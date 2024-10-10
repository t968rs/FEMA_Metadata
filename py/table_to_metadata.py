import os
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
from xml.dom import minidom

from dask.array import unique
from pyproj import CRS
import requests
import logging
import json
from pprint import pprint
from helpers import *
from py.folder_to_file_list import get_file_names


def setup_logger():
    # Create a custom logger
    module_name = __name__ if __name__ != "__main__" else os.path.splitext(os.path.basename(__file__))[0]
    logger = logging.getLogger(module_name)
    # Set the level of this logger. DEBUG is the lowest severity level.
    logger.setLevel(logging.DEBUG)
    # Create handlers
    file_handler = logging.FileHandler(os.path.join(os.getcwd(), f'{module_name}.log'))
    # Create formatters and add it to handlers
    log_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(log_fmt)
    # Add handlers to the logger
    logger.addHandler(file_handler)
    return logger


# then call this function:
logger = setup_logger()


def get_places_dict(df):
    watershed_dict = {}

    # Step 3: Iterate through the DataFrame
    for index, row in df.iterrows():
        hucid = row['HUC8'][:8]
        county = row['County'].replace(' County', '')
        fips_code = row['FIPS']
        cid = row['CID']
        if "unincorporated" in row['Community'].lower():
            community = row['Community'].upper()
        elif "village" in row['Community'].lower():
            community = row['Community'].upper()
            community = f"COMMUNITY {community.replace('VILLAGE OF ', '')}, VILLAGE OF"
        else:
            community = row['Community'].upper()
            community = f"COMMUNITY {community.replace('CITY OF ', '')}, CITY OF"

        if hucid not in watershed_dict:
            watershed_dict[hucid] = {
                'counties': [],
                'fips_codes': [],
                'cids': [],
                'communities': []
            }

        watershed_dict[hucid]['counties'].append(county)
        watershed_dict[hucid]['fips_codes'].append(fips_code)
        watershed_dict[hucid]['cids'].append(cid)
        watershed_dict[hucid]['communities'].append(community)
        unique_counties = list(set(watershed_dict[hucid]['counties']))
        watershed_dict[hucid]['counties'] = unique_counties
    return watershed_dict


def get_specfic_subfolders(root_folder, wildcard):
    """
    Get subfolders that contain a specific wildcard
    :param root_folder: str
    :param wildcard: str
    :return: list
    """
    subfolders = []
    for root, folders, files in os.walk(root_folder):
        for folder in folders:
            if wildcard in folder:
                subfolders.append(os.path.join(root, folder))

    return subfolders


def get_all_sources_from_spatial(folder, filenames):
    shp_paths = []
    for file in filenames:
        shp_path = os.path.join(folder, file + ".shp")
        if os.path.exists(shp_path):
            shp_paths.append(shp_path)

    uniques_source_cits = set()
    for path in shp_paths:
        df = shp_to_df(path)
        unique_vals = get_unique_values(df, 'SOURCE_CIT')
        uniques_source_cits.update(unique_vals)
    return list(uniques_source_cits)


class CreateFEMAxml:
    def __init__(self, excelpath, spatial_root, wildcard, **kwargs):
        self.excel_path = excelpath
        self.lookup_folder = "../static_lookups/"
        self.spatial_root = spatial_root
        self.spatial_wildcard = wildcard
        self.author = "AtkinsRealis"

        self.spatial_folders_lookup = {}
        self.purchases_df = excel_to_df(self.excel_path, sheet_name="MIP Purchase Geographies")
        self.fips_lookup = excel_to_df(self.excel_path, sheet_name="FIPS Lookup")
        self.dfirm_lookup = excel_to_df(self.excel_path, sheet_name="Purchase CID Lookup")
        self.sources_lookup = self._init_sources_lookup()
        self.extents_lookup_draft = excel_to_df(self.excel_path, sheet_name="HUC8_Extents_DRAFT")
        self.extents_lookup_SPCS = excel_to_df(self.excel_path, sheet_name="HUC8_Extents_SPCS")
        self.state_fips = excel_to_df(self.excel_path, sheet_name="State_FIPS_Refs")
        self.state_fips['FIPS'] = self.state_fips['FIPS'].astype(int)
        self.spcs_lookup = excel_to_df(self.excel_path, sheet_name="SPCS_Zone_lookup")
        self.state_fips_code, self.state_name = None, None
        self._init_state_refs()
        self._init_huc8_subfolders()

        print(f"Sources: \n  {self.sources_lookup['SOURCE_CIT'].unique().tolist()}")

    def _init_huc8_subfolders(self):
        # Find subfolders and execute
        spatial_folders_lookup = {}
        root_parent = self.spatial_root
        for root_folder in os.listdir(root_parent):
            if not os.path.isdir(os.path.join(root_parent, root_folder)):
                continue

            contains_digits = any(char.isdigit() for char in root_folder)
            if not contains_digits:
                continue
            number_digits = sum(char.isdigit() for char in root_folder)
            if not number_digits == 8:
                continue
            print(f"Root Folder: {root_folder}, {number_digits}, {contains_digits}")
            huc8_id = "".join([char for char in root_folder if char.isdigit()])
            # print(f" HUC8: {huc8_id}")
            root_folder = os.path.join(root_parent, root_folder)
            subfolders = get_specfic_subfolders(root_folder, self.spatial_wildcard)
            # print(f" Subfolders: {subfolders}")
            if subfolders:
                spatial_folders_lookup[huc8_id] = subfolders[0]
                print(f" HUC8: {huc8_id}, {subfolders[0]}")
        self.spatial_folders_lookup = spatial_folders_lookup

    def _init_sources_lookup(self):
        self.sources_lookup = excel_to_df(self.excel_path, sheet_name="SOURCE_CIT_STATEWIDE", dtype=str)
        template_row = self.sources_lookup.loc[(self.sources_lookup['AUTHOR'] == self.author)].loc[:1]
        template_row = template_row.drop(columns=['SOURCE_CIT', 'DFIRM_ID'])
        logger.debug(f"Template Row: {template_row}")
        print(f"Authors: {self.sources_lookup['AUTHOR'].tolist()}")
        print(f"Author: {self.author}")
        dfirm_dict = self.dfirm_lookup.to_dict(orient='index')
        print(f"DFIRM Dict: {dfirm_dict}")

        # print(f"Template Row: {template_row}\n {type(template_row)}")
        # populate rows for all watersheds
        new_rows = pd.DataFrame(columns=template_row.columns)
        for i, row_dict in dfirm_dict.items():
            dfirm_id = row_dict['DFIRM_ID']
            source_cit = row_dict['SOURCE_CIT']
            title = row_dict['CASE_DESC']
            new_row = template_row.copy()
            new_row['DFIRM_ID'] = dfirm_id
            new_row['SOURCE_CIT'] = source_cit
            new_row['TITLE'] = title
            new_row['PUB_DATE'] = row_dict['COMP_DATE']
            new_row["SRC_DATE"] = row_dict['COMP_DATE']

            # Append the new row to new_rows using pd.concat
            new_rows = pd.concat([new_rows, new_row], ignore_index=True)

        dates = new_rows['PUB_DATE'].tolist() + new_rows['SRC_DATE'].tolist()
        print(f"Dates: {dates}")
        other_rows = self.sources_lookup.loc[(self.sources_lookup['AUTHOR'] != self.author) |
                                             (~self.sources_lookup['SOURCE_CIT'].str.contains("STUDY") &
                                              pd.notna(self.sources_lookup['SOURCE_CIT']) &
                                              (self.sources_lookup['SOURCE_CIT'] != 'nan'))]
        other_rows["DFIRM_ID"] = np.nan
        print(f"Other Rows: {other_rows['SOURCE_CIT'].tolist()}\n")
        all_rows = pd.concat([new_rows, other_rows], ignore_index=True)
        print(f"All Rows: {all_rows['SOURCE_CIT'].tolist()}\n")
        return all_rows

    def _init_state_refs(self):
        # Get state from FIPS codes
        fips_unique = self.purchases_df['FIPS'].unique().tolist()
        states_unique = list(set([str(fips)[:2] for fips in fips_unique]))
        if len(states_unique) > 1:
            raise ValueError(f"Multiple states found in FIPS codes: {states_unique}")
        else:
            self.state_fips_code = int(states_unique[0])
        thistate = self.state_fips[self.state_fips['FIPS'] == self.state_fips_code]
        self.state_name = thistate['State'].values[0]
        print(f"State {self.state_fips_code}: {self.state_name}")

    def create_places_sub_xml(self, inf_dict, **kwargs) -> ET.ElementTree:
        place = ET.Element("place")
        tree = ET.ElementTree(place)

        placekt = ET.SubElement(place, 'placekt')
        placekt.text = "None"
        for k in ["REGION 07", "STATE IA"]:
            placekey = ET.SubElement(place, 'placekey')
            placekey.text = k

        if "DFIRM ID" in kwargs:
            placekey = ET.SubElement(place, 'placekey')
            placekey.text = f"FEMA-CID {kwargs['DFIRM ID']}"

        for county in inf_dict['counties']:
            placekey = ET.SubElement(place, 'placekey')
            placekey.text = f"COUNTY {county.upper()}"
            placekey2 = ET.SubElement(place, 'placekey')
            placekey2.text = f"COUNTY-FIPS "
            county_name = county + " County"
            try:
                fips_code = self.fips_lookup.loc[self.fips_lookup['County Name'] == county_name, 'FIPS Code'].values[0]
                placekey2.text += f"{fips_code}"
            except IndexError:
                placekey2.text += "None"
                print(f"County {county} not found in FIPS lookup")

        for community in inf_dict['communities']:
            placekey = ET.SubElement(place, 'placekey')
            placekey.text = community

        for cid in inf_dict['cids']:
            placekey = ET.SubElement(place, 'placekey')
            placekey.text = f"FEMA-CID {cid}"

        tree_str = ET.tostring(tree.getroot(), encoding='utf-8').decode('utf-8')
        sec_element = ET.fromstring(remove_extraneous_spacing(tree_str))
        # print(f"Section 125: {ET.tostring(sec_element, encoding='utf-8')}")

        tree = ET.ElementTree(sec_element)

        return tree

    def create_ea_info(self, ea_list: list[dict], spatial_list) -> ET.ElementTree:

        # Clean up the EA list whitespace
        cleaned_ea_list = []
        for ea_dict in ea_list:
            new_dict = {}
            for k, v in ea_dict.items():
                if isinstance(v, list):
                    clean_list = []
                    for item in v:
                        clean_list.append(remove_whitespace(item))
                    new_dict[k] = clean_list
                else:
                    clean_string = remove_whitespace(v)
                    new_dict[k] = clean_string
            cleaned_ea_list.append(new_dict)

        eainfo = ET.Element("eainfo")
        ea_list_detailed = [ea_dict for ea_dict in ea_list if "enttypl" in ea_dict]
        ea_list_overview = [ea_dict for ea_dict in ea_list if "enttypl" not in ea_dict]

        # Pre-Process EA based on spatial files
        # Remove entries not in spatial files
        if spatial_list:
            spatial_list_lower = [s.lower().replace(" ", "") for s in spatial_list]
            new_ea_list = []
            for ea_dict in ea_list_detailed:
                # print(f"EA Dict: {ea_dict}")
                if "enttypl" in ea_dict:
                    sname = ea_dict.get('enttypl', "None")
                    sname = sname.lower().replace(" ", "")
                    if sname in spatial_list_lower:
                        new_ea_list.append(ea_dict)
                else:
                    new_ea_list.append(ea_dict)
            ea_list_detailed = new_ea_list

        for i, ea_dict in enumerate(ea_list_detailed):
            if "enttypl" in ea_dict:
                detailed = ET.SubElement(eainfo, 'detailed')
                enttyp = ET.SubElement(detailed, 'enttyp')
                enttypl = ET.SubElement(enttyp, 'enttypl')
                enttypl.text = ea_dict['enttypl']
                enttypd = ET.SubElement(enttyp, 'enttypd')
                enttypd.text = ea_dict['enttypd']
                enttypds = ET.SubElement(enttyp, 'enttypds')
                enttypds.text = ea_dict['enttypds']
            else:
                raise ValueError(f"Invalid EA Info: {ea_dict}")
        overview = ET.SubElement(eainfo, 'overview')
        for i, ea_dict in enumerate(ea_list_overview):
            if "enttypl" not in ea_dict and "eaover" in ea_dict:
                eaover = ET.SubElement(overview, 'eaover')
                eaover.text = ea_dict['eaover'].strip()
                # print(f"EA OVER: {ea_dict['eaover']}")
                if isinstance(ea_dict.get('eadetcit'), list):
                    for cit in ea_dict['eadetcit']:
                        eadetcit = ET.SubElement(overview, 'eadetcit')
                        eadetcit.text = cit.strip()
                else:
                    eadetcit = ET.SubElement(overview, 'eadetcit')
                    eadetcit.text = ea_dict.get('eadetcit', 'False')

        return ET.ElementTree(eainfo), spatial_list

    def create_sources_xml(self, **kwargs) -> ET.ElementTree:

        # Create a new tree with root element "lineage"
        lineage = ET.Element("lineage")

        used_source_cit = kwargs.get("used")
        if used_source_cit:
            all_sources = [s for s in self.sources_lookup['SOURCE_CIT'].tolist() if s in used_source_cit or "TOPO" in s]
        else:
            all_sources = self.sources_lookup['SOURCE_CIT'].tolist()
        # self.sources_lookup.to_excel(f"ALL_SOURCES_{kwargs.get("DFIRM ID", 1)}.xlsx", index=False)
        print(f"Sources: {all_sources}")
        unique_non_study = [s for s in all_sources if "STUDY" not in s and s != "nan"]
        target_row = self.sources_lookup.loc[self.sources_lookup['SOURCE_CIT'] == kwargs.get("SOURCE_CIT")]
        logger.debug(f"Target Row: {target_row}")
        other_rows = self.sources_lookup.loc[self.sources_lookup['SOURCE_CIT'].isin(unique_non_study)]
        sources_to_add = pd.concat([target_row, other_rows], ignore_index=True)
        print(f"Adding {sources_to_add['SOURCE_CIT'].tolist()}")
        # sources_to_add.to_excel(f"SOURCES_to_add_{kwargs.get("DFIRM ID", 1)}.xlsx", index=False)

        if kwargs.get("spatial_files"):
            spatial_files = kwargs.get("spatial_files")
            if spatial_files:
                target_row['CONTRIB'] = ", ".join(spatial_files)

        for index, row in sources_to_add.iterrows():
            srcinfo = ET.SubElement(lineage, 'srcinfo')

            srccite = ET.SubElement(srcinfo, 'srccite')
            citeinfo = ET.SubElement(srccite, 'citeinfo')

            origin = ET.SubElement(citeinfo, 'origin')
            origin.text = row.get('PUBLISHER', 'False')

            pubdate = ET.SubElement(citeinfo, 'pubdate')
            pubdate.text = row.get('PUB_DATE', 'False')

            title = ET.SubElement(citeinfo, 'title')
            title.text = row.get('TITLE', 'False')

            geoform = ET.SubElement(citeinfo, 'geoform')
            geoform.text = "map"

            pubinfo = ET.SubElement(citeinfo, 'pubinfo')
            pubplace = ET.SubElement(pubinfo, 'pubplace')
            pubplace.text = row.get('PUB_PLACE', 'False')

            publish = ET.SubElement(pubinfo, 'publish')
            publish.text = "Federal Emergency Management Agency"

            othercit = ET.SubElement(citeinfo, 'othercit')
            othercit.text = f"Effective FIS and FIRM from State of {self.state_name}"  # get from MIP purchase GEOGRAPHIES

            srcscale = ET.SubElement(srcinfo, 'srcscale')
            srcscale.text = row.get('srcscale', '1:24000').split(":")[1]

            typesrc = ET.SubElement(srcinfo, 'typesrc')
            typesrc.text = row.get('MEDIA', 'Digital')

            srctime = ET.SubElement(srcinfo, 'srctime')
            timeinfo = ET.SubElement(srctime, 'timeinfo')
            sngdate = ET.SubElement(timeinfo, 'sngdate')
            caldate = ET.SubElement(sngdate, 'caldate')
            caldate.text = row.get("PUB_DATE", 'False')

            srccurr = ET.SubElement(srctime, 'srccurr')
            srccurr.text = row.get('DATE_REF', 'Publication Date')

            srccitea = ET.SubElement(srcinfo, 'srccitea')
            srccitea.text = row.get('SOURCE_CIT', 'False')

            srccontr = ET.SubElement(srcinfo, 'srccontr')
            srccontr.text = row.get('CONTRIB', '')

        test_tree = ET.ElementTree(lineage)
        write_xml(test_tree, "SOURCES_test.xml")

        # Get source info for this source only
        notes = target_row['NOTES'].values
        notes = notes.tolist()
        print(f"{kwargs.get("SOURCE_CIT")} NOTES: {notes}, type: {type(notes)}, len: {len(notes)}")

        # Create procstep element
        procstep = ET.SubElement(lineage, 'procstep')
        procdesc = ET.SubElement(procstep, 'procdesc')
        if notes:
            procdesc.text = notes[0]
        else:
            procdesc.text = ""
        procdate = ET.SubElement(procstep, 'procdate')
        procdate.text = self.sources_lookup.loc[self.sources_lookup['SOURCE_CIT'] ==
                                                kwargs.get("SOURCE_CIT"), 'SRC_DATE'].values[0]

        tree = ET.ElementTree(lineage)
        tree_str = ET.tostring(tree.getroot(), encoding='utf-8').decode('utf-8')
        sec_element = ET.fromstring(remove_extraneous_spacing(tree_str))
        # print(f"Section 264: {ET.tostring(sec_element, encoding='utf-8')}")

        tree = ET.ElementTree(sec_element)

        return tree

    def create_extents_xml(self, area_id, field_with_area) -> ET.ElementTree:
        start_str = "spdom"
        # Create a new tree with root element "lineage"
        root = ET.Element(start_str)
        this_df = self.extents_lookup_draft.loc[self.extents_lookup_draft[field_with_area] == area_id]
        bounding = ET.SubElement(root, 'bounding')
        westbc = ET.SubElement(bounding, 'westbc')
        westbc.text = str(round(this_df['westbc'].values[0] - 0.01, 3))
        eastbc = ET.SubElement(bounding, 'eastbc')
        eastbc.text = str(round(this_df['eastbc'].values[0] + 0.01, 3))
        northbc = ET.SubElement(bounding, 'northbc')
        northbc.text = str(round(this_df['northbc'].values[0] + 0.01, 3))
        southbc = ET.SubElement(bounding, 'southbc')
        southbc.text = str(round(this_df['southbc'].values[0] - 0.01, 3))

        tree = ET.ElementTree(root)
        test_tree = ET.tostring(tree.getroot(), encoding='utf-8').decode('utf-8')
        xml_str = remove_extraneous_spacing(test_tree)
        xml_str = pretty_print_xml(xml_str)
        # print(f"Section 292: {xml_str}")
        pprint(xml_str)

        return ET.ElementTree(root)

    def create_spcs_refs_dict(self) -> dict:
        unique_epsgs = self.extents_lookup_SPCS['crs'].unique().tolist()
        print(f'\nThis state: {self.state_name}')
        state_spcs_df = self.spcs_lookup[self.spcs_lookup["State"] == self.state_name]
        print(f"State Rows: {state_spcs_df}")
        horizontal_crs_lookup = {epsg: {"central_meridian": None, "latitude_of_origin": None, "easting": None,
                                        "northing": None, "spcs_code": None, "standard_parallel": None,
                                        "horizontal_unit": None,
                                        "spcs_grid": None, "semi_axis": None, "denflat": None} for epsg in unique_epsgs}
        for epsg_code in unique_epsgs:
            # Get CRS Info
            print(f"EPSG: {epsg_code}")
            crs_info = CRS.from_user_input(int(epsg_code))
            print(f' CRS Info: {crs_info}')
            print(f' CRS Name: {crs_info.name}')
            crs_json = crs_info.to_json_dict()

            # Get SPCS Code
            zone_name, zone_number = None, None
            cardinal_directions = ["north", "south", "east", "west"]
            for direction in cardinal_directions:
                # print(f" Direction: {direction}, {crs_json['name']}")
                if direction in crs_json["name"].lower():
                    zone_name = direction.title()
                    break
            if zone_name:
                for i, row in state_spcs_df.iterrows():
                    if zone_name.lower() in row['Zone_Name'].lower():
                        zone_name = row['Zone_Name']
                        if row['Zone_Number'] != 0:
                            zone_number = row['Zone_Number']
                        break
                    break

            if zone_name:
                horizontal_crs_lookup[epsg_code]["spcs_code"] = \
                    state_spcs_df.loc[state_spcs_df['Zone_Name'] == zone_name, 'SPCS_ID'].values[0]
                if zone_number:
                    horizontal_crs_lookup[epsg_code]["spcs_code"] += f" {zone_number}"
                print(f"  SPCS Code: {horizontal_crs_lookup[epsg_code]['spcs_code']}")
            else:
                horizontal_crs_lookup[epsg_code]["spcs_code"] = (
                    state_spcs_df.loc[state_spcs_df['State'] == self.state_name, 'SPCS_ID'].values)[0]

            # Get geoid
            if "conversion" in crs_json:
                conversion_name = crs_json["conversion"]["name"]
                if "spcs" in conversion_name.lower():
                    horizontal_crs_lookup[epsg_code]["grid_sys_name"] = "State Plane Coordinate System 1983"
                if (("us " in conversion_name.lower() or "us_" in conversion_name.lower() or
                     "survey" in conversion_name.lower()) and
                        ("feet" in conversion_name.lower() or "foot" in conversion_name.lower())):
                    horizontal_crs_lookup[epsg_code]["horizontal_unit"] = "survey feet"
                elif "feet" in conversion_name.lower() or "foot" in conversion_name.lower():
                    horizontal_crs_lookup[epsg_code]["horizontal_unit"] = "international feet"
                elif "meter" in conversion_name.lower():
                    horizontal_crs_lookup[epsg_code]["horizontal_unit"] = "meters"
                if "method" in crs_json["conversion"]:
                    method = crs_json["conversion"]["method"]
                    for k, v in method.items():
                        print(f"  Method: {k}, {v}")
                    if "lambert" in method.get("name", None).lower():
                        horizontal_crs_lookup[epsg_code]["spcs_grid"] = "lambertc"
            if "base_crs" in crs_json:
                if "datum" in crs_json["base_crs"]:
                    datum = crs_json["base_crs"]["datum"]
                    if "ellipsoid" in datum:
                        ellipsoid = datum["ellipsoid"]
                        if "semi_major_axis" in ellipsoid:
                            horizontal_crs_lookup[epsg_code]["semi_axis"] = f"{ellipsoid['semi_major_axis']}"
                        if "inverse_flattening" in ellipsoid:
                            horizontal_crs_lookup[epsg_code]["denflat"] = f"{ellipsoid['inverse_flattening']}"

            # Get parameters list
            parameters = crs_json['conversion']['parameters']
            for param in parameters:
                if "longitude" in param["name"].lower() and "false" in param["name"].lower():
                    horizontal_crs_lookup[epsg_code]['central_meridian'] = f"{param["value"]}"
                elif "latitude" in param["name"].lower() and "false" in param["name"].lower():
                    horizontal_crs_lookup[epsg_code]['latitude_of_origin'] = f"{param["value"]}"
                elif "latitude" in param["name"].lower() and "standard" in param["name"].lower():
                    any_digits = False
                    for c in param["name"]:
                        if c.isdigit():
                            any_digits = True
                            break
                    if any_digits:
                        if "1" in param["name"]:
                            horizontal_crs_lookup[epsg_code]['standard_parallel'] = f"{param["value"]}"
                    else:
                        horizontal_crs_lookup[epsg_code]['standard_parallel'] = f"{param["value"]}"
                elif "easting" in param["name"].lower() and "false" in param["name"].lower():
                    horizontal_crs_lookup[epsg_code]['easting'] = str(param["value"])
                elif "northing" in param["name"].lower() and "false" in param["name"].lower():
                    horizontal_crs_lookup[epsg_code]['northing'] = str(param["value"])
            # print(f"SPCS Lookup: {horizontal_crs_lookup[epsg_code]}")

        return horizontal_crs_lookup

    def create_spcs_xml(self, epsg_code, info_dict) -> ET.ElementTree:
        print(f'\nEPSG: {epsg_code}, {info_dict}')

        # Create a new tree with root element start_str
        root = ET.Element("horizsys")
        planar = ET.SubElement(root, 'planar')

        # Create datum model and planar sub-elements
        # Create planar gridsys sub-element
        gridsys = ET.SubElement(planar, 'gridsys')
        gridsysn = ET.SubElement(gridsys, 'gridsysn')
        gridsysn.text = info_dict.get("grid_sys_name", "State Plane Coordinate System 1983")
        spcs = ET.SubElement(gridsys, 'spcs')
        spcs_zone = ET.SubElement(spcs, 'spcszone')
        spcs_zone.text = str(info_dict.get("spcs_code", None))

        # Planar Coordinate Encoding Method
        planci = ET.SubElement(planar, 'planci')
        plance = ET.SubElement(planci, 'plance')
        plance.text = "coordinate pair"
        coordrep = ET.SubElement(planci, 'coordrep')
        absres = ET.SubElement(coordrep, 'absres')
        absres.text = "0.0025"
        ordres = ET.SubElement(coordrep, 'ordres')
        ordres.text = "0.0025"
        plandu = ET.SubElement(planci, 'plandu')
        plandu.text = info_dict.get("horizontal_unit", "survey feet")

        spcs_grid_elem = ET.SubElement(spcs, info_dict.get("spcs_grid", "lambertc"))
        # Create geodetic model sub-element
        geodetic = ET.SubElement(root, 'geodetic')
        horizdn = ET.SubElement(geodetic, 'horizdn')
        horizdn.text = "North American Datum of 1983"
        ellips = ET.SubElement(geodetic, 'ellips')
        ellips.text = "Geodetic Reference System 80"
        semiaxis = ET.SubElement(geodetic, 'semiaxis')
        semiaxis.text = info_dict.get("semi_axis", None)
        denflat = ET.SubElement(geodetic, 'denflat')
        denflat.text = info_dict.get("denflat", None)

        # Add specific SPCS elements
        stdparll = ET.SubElement(spcs_grid_elem, 'stdparll')
        stdparll.text = info_dict.get("standard_parallel", None)
        longcm = ET.SubElement(spcs_grid_elem, 'longcm')
        longcm.text = info_dict["central_meridian"]
        latprjo = ET.SubElement(spcs_grid_elem, 'latprjo')
        latprjo.text = info_dict["latitude_of_origin"]

        feast = ET.SubElement(spcs_grid_elem, 'feast')
        feast.text = info_dict["easting"]
        fnorth = ET.SubElement(spcs_grid_elem, 'fnorth')
        fnorth.text = info_dict["northing"]

        tree_str = pretty_print_xml(ET.tostring(root, encoding='utf-8').decode('utf-8'))
        # print(f"Section 484: {tree_str}")
        return ET.ElementTree(ET.fromstring(tree_str))

    def create_fema_metadata(self):
        w_dict = get_places_dict(self.purchases_df)
        #
        for watershed, details in w_dict.items():
            # Get watershed info
            print(f"\nWatershed: {watershed}")
            matching_rows = self.dfirm_lookup.loc[self.dfirm_lookup['HUC8'] == watershed]
            if matching_rows.empty:
                print(f"\nNo matching rows for {watershed}")
                continue
            DFIRM_ID = matching_rows['DFIRM_ID'].values[0]
            SOURCE_CIT = matching_rows['SOURCE_CIT'].values[0]
            print(f'\n{watershed}: {DFIRM_ID}, {SOURCE_CIT}')

            # Fill out missing values into DF
            self.sources_lookup = fill_df_with_values(self.sources_lookup, ["DFIRM_ID", "SOURCE_CIT"],
                                                      **{"DFIRM_ID": DFIRM_ID, "SOURCE_CIT": SOURCE_CIT})

            # Get spatial files, if folder provided
            spatial_subfolder = self.spatial_folders_lookup.get(watershed, "")
            print(f"\nSpatial Subfolder: {spatial_subfolder}")
            spatial_files = None
            SOURCE_CIT_used = []
            if spatial_subfolder and os.path.exists(spatial_subfolder):
                spatial_files = get_file_names(spatial_subfolder, ".shp")
                SOURCE_CIT_used = get_all_sources_from_spatial(spatial_subfolder, spatial_files)
                print(f"Spatial Files: {spatial_files}")

            # EA Info
            ea_path = f"{self.lookup_folder}EA_Info.json"
            with open(ea_path, "r") as ea:
                ea_list = json.load(ea)
                eainfo_tree, spatial_list = self.create_ea_info(ea_list, spatial_files)
                out_folder = "../ea_info/"
                os.makedirs(out_folder, exist_ok=True)
                write_xml(eainfo_tree, f"{out_folder}{DFIRM_ID}_EA.xml")

            place_tree = self.create_places_sub_xml(details, **{"DFIRM ID": DFIRM_ID})
            # print(f"Section: {ET.tostring(place_tree.getroot(), encoding='utf-8')}")
            out_folder = "../places/"
            out_xml = out_folder + f"{DFIRM_ID}_PLACES.xml"
            write_xml(place_tree, out_xml)

            sources_tree = self.create_sources_xml(**{"DFIRM ID": DFIRM_ID,
                                                      "SOURCE_CIT": SOURCE_CIT, "used": SOURCE_CIT_used,
                                                      "spatial_files": spatial_files})
            out_folder = "../source_cit/"
            os.makedirs(out_folder, exist_ok=True)
            output_file = f"{out_folder}{DFIRM_ID}_SOURCE_CIT.xml"
            write_xml(sources_tree, output_file)

            # Extents
            out_folder = "../extents/"
            os.makedirs(out_folder, exist_ok=True)
            extents_tree = self.create_extents_xml(watershed, "HUC8")
            output_file = f"{out_folder}{DFIRM_ID}_EXTENTS.xml"
            write_xml(extents_tree, output_file)

            # SPCS
            spcs_lookup = self.create_spcs_refs_dict()
            for epsg, info_dict in spcs_lookup.items():
                spcs_tree = self.create_spcs_xml(epsg, info_dict)
                out_folder = "../spcs/"
                os.makedirs(out_folder, exist_ok=True)
                output_file = f"{out_folder}{epsg}_SPCS.xml"
                write_xml(spcs_tree, output_file)


if __name__ == "__main__":
    excel_path = "../Iowa_BLE_Purchase_Geographies.xlsx"
    spatial_files_root = r"E:\Iowa_3B\03_delivery"
    spatial_wildcard = "DRAFT"
    fema_xml = CreateFEMAxml(excel_path, spatial_files_root, spatial_wildcard)
    fema_xml.create_fema_metadata()
