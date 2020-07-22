import os
import re
import ogr
from lib.science_base import get_nhdhr_url
from lib.download import download_unzip
from lib.file_geodatabase import export_feature_class, copy_attributes, export_table
from lib.util import safe_makedirs
from lib.shapefile import get_geometry_union

# NHDPlus HR Value Added Attributes (VAA) to be copied to the NHDFlowline feature class
flowline_fields = [
    'AreaSqKm',
    'TotDASqKm',
    'Slope',
    'MaxElevSmo',
    'MInElevSmo'
]


def clean_nhd_data(huc, download_folder, unzip_folder, out_dir, out_epsg, force_download):

    filegdb = download_unzip_nhd(huc, download_folder, unzip_folder, out_epsg, force_download)

    # This is the dictionary of cleaned feature classes produced by this processed
    featureclasses = {}

    # Export the watershed boundaries, using an attribute filter if desired HUC is smaller than the 4 digit download
    for digits in [2, 4, 6, 8, 10, 12]:
        fclass = 'WBDHU{}'.format(digits)

        operator = 'LIKE' if digits > len(huc) else '='
        wildcard = '%' if digits > len(huc) else ''
        attribute_filter = "HUC{} {} '{}{}'".format(digits, operator, huc[:digits], wildcard) if digits >= len(huc) else None

        featureclasses[fclass] = export_feature_class(filegdb, fclass, out_dir, out_epsg, None, attribute_filter, None)

    # Retrieve the watershed boundary if processing 8 digit HUC
    boundary = get_geometry_union(featureclasses['WBDHU{}'.format(len(huc))], out_epsg) if len(huc) > 4 else None

    # Retrieve the name of the HUC
    driver = ogr.GetDriverByName("ESRI Shapefile")
    datasource = driver.Open(featureclasses['WBDHU{}'.format(len(huc))], 0)
    layer = datasource.GetLayer()
    huc_name = layer[0].GetField('name')
    datasource = None

    # NHDFlowlines and incorporate the desired value added attributes from the VAA geodatabase table into the NHD flow lines
    featureclasses['NHDFlowline'] = export_feature_class(filegdb, 'NHDFlowline', out_dir, out_epsg, None, None, boundary)
    copy_attributes(filegdb, 'NHDPlusFlowlineVAA', featureclasses['NHDFlowline'], 'NHDPlusID', flowline_fields, "ReachCode LIKE '{}%'".format(huc))

    # Export the river area polyline feature class, filtering by boundary if required
    featureclasses['NHDArea'] = export_feature_class(filegdb, 'NHDArea', out_dir, out_epsg, None, None, boundary)
    featureclasses['NHDWaterbody'] = export_feature_class(filegdb, 'NHDWaterbody', out_dir, out_epsg, None, None, boundary)
    featureclasses['NHDPlusCatchment'] = export_feature_class(filegdb, 'NHDPlusCatchment', out_dir, out_epsg, None, None, boundary)

    db_path = os.path.join(out_dir, 'nhd_data.sqlite')
    export_table(filegdb, 'NHDPlusFlowlineVAA', db_path, None, "ReachCode LIKE '{}%'".format(huc))

    return featureclasses, db_path, huc_name


def download_unzip_nhd(huc, download_folder, unzip_folder, out_epsg, force_download):

    nhd_url = get_nhdhr_url(huc[:4])
    safe_makedirs(download_folder)
    safe_makedirs(unzip_folder)

    nhd_unzip_folder = download_unzip(nhd_url, download_folder, unzip_folder, force_download)

    # get the gdb folder
    def matchGdb(fname):
        fpath = os.path.join(nhd_unzip_folder, fname)
        return os.path.isdir(fpath) and re.match(r"^.*\.gdb", fpath)

    try:
        filegdb = os.path.join(nhd_unzip_folder, next(filter(matchGdb, os.listdir(nhd_unzip_folder))))
    except Exception:
        raise Exception("Could not find the GDB folder inside: {}".format(nhd_unzip_folder))

    return filegdb