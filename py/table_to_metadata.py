import os
import pandas as pd
import numpy as np
import xml.etree.ElementTree as ET
from xml.dom import minidom
import json
from pprint import pprint
from helpers import *

TO_INSERT = ["place", "lineage"]


def update_ea_info(tree, data: list) -> ET.ElementTree:
    # Find the <eainfo> tag in the XML template
    root = tree.getroot()
    eainfo_elem = root.find(".//eainfo")

    # Update the XML template with data from JSON
    for item in data:
        detailed_elem = eainfo_elem.find(".//detailed")
        if detailed_elem is not None:
            enttyp_elem = detailed_elem.find(".//enttyp")
            if enttyp_elem is not None:
                update_xml_from_dict(enttyp_elem, item)
        overview_elem = eainfo_elem.find(".//overview")
        if overview_elem is not None:
            update_xml_from_dict(overview_elem, item)
    return tree


class CreateFEMAxml:
    def __init__(self):
        self.excel_path = "../Area_1A_Purchase_Geographies_ADDS.xlsx"
        self.lookup_folder = "../static_lookups/"
        self.author = "AtkinsRealis"

        self.purchases_df = excel_to_df(self.excel_path, sheet_name="MIP Purchase Geographies")
        self.fips_lookup = excel_to_df(self.excel_path, sheet_name="FIPS Lookup")
        self.dfirm_lookup = excel_to_df(self.excel_path, sheet_name="Purchase CID Lookup")
        self.sources_lookup = self._init_sources_lookup()
        self.extents_lookup = excel_to_df(self.excel_path, sheet_name="HUC8_Extents")

        print(self.sources_lookup['SOURCE_CIT'].unique().tolist())
        unique_dates = list(
            set(self.sources_lookup['SRC_DATE'].dropna().unique()).union(set(
                self.sources_lookup['PUB_DATE'].dropna().unique())))

    def _init_sources_lookup(self):
        self.sources_lookup = excel_to_df(self.excel_path, sheet_name="SOURCE_CIT_STATEWIDE", dtype=str)
        template_row = (self.sources_lookup.loc[self.sources_lookup['AUTHOR'] == self.author]
                        .drop(columns=['SOURCE_CIT', 'DFIRM_ID']))
        dfirm_dict = self.dfirm_lookup.to_dict(orient='index')

        print(f"Template Row: {template_row}\n {type(template_row)}")
        # populate rows for all watersheds
        new_rows = pd.DataFrame(columns=template_row.columns)
        for i, row_dict in dfirm_dict.items():
            dfirm_id = row_dict['DFIRM_ID']
            source_cit = row_dict['SOURCE_CIT']
            new_row = template_row.copy()
            new_row['DFIRM_ID'] = dfirm_id
            new_row['SOURCE_CIT'] = source_cit

            # Append the new row to new_rows using pd.concat
            new_rows = pd.concat([new_rows, new_row], ignore_index=True)

        other_rows = self.sources_lookup.loc[self.sources_lookup['AUTHOR'] != self.author]
        return pd.concat([new_rows, other_rows], ignore_index=True)
    def get_places_dict(self, df):
        watershed_dict = {}

        # Step 3: Iterate through the DataFrame
        for index, row in df.iterrows():
            hucid = row['Watershed']
            county = row['County'].replace(' County', '')
            fips_code = row['FIPS']
            cid = row['CID']
            if "unincorporated" in row['Community'].lower():
                community = row['Community'].upper()
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

    def remove_nan_srcinfo(self, tree: ET.ElementTree, start_str=None) -> ET.ElementTree:
        start_str = "lineage"
        tree = extract_subtree_within_tag(tree, start_str)
        root = tree.getroot()
        start_tag = root.find(start_str)
        if start_tag is None:
            start_tag = ET.Element(start_str)
            root.append(start_tag)

        # Create a dictionary to map existing srcinfo elements by a unique identifier (e.g., srccitea)
        existing_srcinfo = {srcinfo.find('srccitea').text: srcinfo for srcinfo in start_tag.findall('srcinfo')}

        # Iterate over the dictionary and remove elements with "nan" srccitea
        for key, srcinfo in existing_srcinfo.items():
            if key in ["", " ", None, "nan", np.nan]:
                start_tag.remove(srcinfo)

        return tree

    def consolidate_subs_trees(self, tree: ET.ElementTree, umbrella_tag: str, tag_bookend: str) -> ET.ElementTree:
        root = tree.getroot()
        umbrella = root.find(f'.//{umbrella_tag}')
        if umbrella is None:
            raise ValueError(umbrella_tag, " not found in the XML tree")

        # Find all procstep elements
        tag_many = umbrella.findall(tag_bookend)

        if not tag_many:
            return tree

        # Create a new procstep element
        tag_dedupe = ET.Element(tag_bookend)

        # Append all child elements of the found procstep elements to the new procstep element
        for procstep in tag_many:
            for child in list(procstep):
                tag_dedupe.append(child)

        # Remove the old procstep elements from the XML tree
        for procstep in tag_many:
            umbrella.remove(procstep)

        # Append the new procstep element to the XML tree
        umbrella.append(tag_dedupe)

        return tree

    def extract_subtree_within_tag(self, tree, tag):
        root = tree.getroot()
        start_element = root.find(f".//{tag}")

        if start_element is None:
            print(f"TREE: {ET.tostring(root, encoding='utf-8')}")
            raise ValueError(f"Tag '{tag}' not found in the XML tree")

        # Find the parent of the start element
        parent_map = {c: p for p in tree.iter() for c in p}
        parent = parent_map.get(start_element)

        # Extract elements within the start tag
        extracted_elements = []
        found_start = False
        for elem in parent:
            if elem == start_element:
                found_start = True
            if found_start:
                extracted_elements.append(elem)
            if elem.tag == tag and elem != start_element:
                break

        # Create a new tree with the extracted elements
        new_root = ET.Element(parent.tag)
        for elem in extracted_elements:
            if elem not in new_root:
                new_root.append(elem)

        return ET.ElementTree(new_root)

    def create_places_sub_xml(self, inf_dict, tree: ET.ElementTree, **kwargs) -> ET.ElementTree:
        start_str = "keywords"
        tree = extract_subtree_within_tag(tree, start_str)
        root = tree.getroot()
        start_tag = root.find(start_str)
        if start_tag is None:
            start_tag = ET.Element(start_str)

        place = ET.SubElement(start_tag, 'place')
        placekt = ET.SubElement(place, 'placekt')
        placekt.text = ""
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
        print(f"Section 146: {ET.tostring(sec_element, encoding='utf-8')}")

        tree = ET.ElementTree(sec_element)

        return tree

    def create_sources_xml(self, **kwargs) -> ET.ElementTree:
        start_str = "lineage"
        # Create a new tree with root element "lineage"
        root = ET.Element(start_str)

        # Get state from FIPS codes
        state = None
        fips_unique = self.purchases_df['FIPS'].unique().tolist()
        states_unique = list(set([str(fips)[:2] for fips in fips_unique]))
        if len(states_unique) > 1:
            raise ValueError(f"Multiple states found in FIPS codes: {states_unique}")
        else:
            state = states_unique[0]

        unique_non_study = self.sources_lookup['SOURCE_CIT'].unique().tolist()
        unique_non_study = [s for s in unique_non_study if "STUDY" not in s]
        target_row = self.sources_lookup.loc[self.sources_lookup['SOURCE_CIT'] == kwargs.get("SOURCE_CIT")]
        other_rows = self.sources_lookup.loc[self.sources_lookup['SOURCE_CIT'].isin(unique_non_study)]
        sources_to_add = pd.concat([target_row, other_rows], ignore_index=True)

        for index, row in sources_to_add.iterrows():
            srcinfo = ET.SubElement(root, 'srcinfo')

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
            othercit.text = f"Effective FIS and FIRM from State of {state}"  # get from MIP purchase GEOGRAPHIES

            srcscale = ET.SubElement(srcinfo, 'srcscale')
            srcscale.text = row.get('srcscale', '1:24000').split(":")[1]

            typesrc = ET.SubElement(srcinfo, 'typesrc')
            typesrc.text = row.get('MEDIA', 'Digital')

            srctime = ET.SubElement(srcinfo, 'srctime')
            timeinfo = ET.SubElement(srctime, 'timeinfo')
            sngdate = ET.SubElement(timeinfo, 'sngdate')
            caldate = ET.SubElement(sngdate, 'caldate')
            caldate.text = row.get('caldate', 'False')

            srccurr = ET.SubElement(srctime, 'srccurr')
            srccurr.text = row.get('DATE_REF', 'Publication Date')

            srccitea = ET.SubElement(srcinfo, 'srccitea')
            srccitea.text = row.get('SOURCE_CIT', 'False')

            srccontr = ET.SubElement(srcinfo, 'srccontr')
            srccontr.text = row.get('CONTRIB', '')

        test_tree = ET.ElementTree(root)
        write_xml(test_tree, "SOURCES_test.xml")

        # Get source info for this source only
        notes = target_row['NOTES'].values
        notes = notes.tolist()
        print(f"{kwargs.get("SOURCE_CIT")} NOTES: {notes}, type: {type(notes)}, len: {len(notes)}")

        # Create procstep element
        procstep = ET.SubElement(root, 'procstep')
        procdesc = ET.SubElement(procstep, 'procdesc')
        if notes:
            procdesc.text = notes[0]
        else:
            procdesc.text = ""
        procdate = ET.SubElement(procstep, 'procdate')
        procdate.text = self.sources_lookup.loc[self.sources_lookup['SOURCE_CIT'] ==
                                                kwargs.get("SOURCE_CIT"), 'SRC_DATE'].values[0]

        # Extract the sources from the XML tree
        # all_sources = extract_all_of_tag(ET.tostring(tree.getroot(), encoding='utf-8'), "srcinfo")
        # all_sources = list(set(all_sources))
        # print(f"  {len(all_sources)} Sources")

        # Create a dictionary to map existing srcinfo elements by a unique identifier (e.g., title)
        # lineage_tree = add_parent_tag_to_tree(tree, start_str)
        # clean_tree = remove_nan_srcinfo(lineage_tree)

        tree = ET.ElementTree(root)
        tree_str = ET.tostring(tree.getroot(), encoding='utf-8').decode('utf-8')
        sec_element = ET.fromstring(remove_extraneous_spacing(tree_str))
        print(f"Section 264: {ET.tostring(sec_element, encoding='utf-8')}")

        tree = ET.ElementTree(sec_element)

        return tree

    def create_extents_xml(self, area_id, field_with_area) -> ET.ElementTree:
        start_str = "spdom"
        # Create a new tree with root element "lineage"
        root = ET.Element(start_str)
        this_df = self.extents_lookup.loc[self.extents_lookup[field_with_area] == area_id]

        westbc = ET.SubElement(root, 'westbc')
        westbc.text = str(round(this_df['westbc'].values[0], 3))
        southbc = ET.SubElement(root, 'southbc')
        southbc.text = str(round(this_df['southbc'].values[0], 3))
        eastbc = ET.SubElement(root, 'eastbc')
        eastbc.text = str(round(this_df['eastbc'].values[0], 3))
        northbc = ET.SubElement(root, 'northbc')
        northbc.text = str(round(this_df['northbc'].values[0], 3))

        tree = ET.ElementTree(root)
        test_tree = ET.tostring(tree.getroot(), encoding='utf-8').decode('utf-8')
        xml_str = remove_extraneous_spacing(test_tree)
        xml_str = pretty_print_xml(xml_str)
        print(f"Section 292: {xml_str}")
        pprint(xml_str)

        return ET.ElementTree(root)

    def create_fema_metadata(self):
        w_dict = self.get_places_dict(self.purchases_df)
        #
        xml_files = [self.lookup_folder + f for f in os.listdir(self.lookup_folder) if f.endswith(".xml")]
        print(f"XML Files: {xml_files}")

        for template_path in xml_files:
            stage = "DRAFT" if "DRAFT" in template_path else "Hydraulics"
            for watershed, details in w_dict.items():
                try:
                    template_tree = ET.parse(template_path)
                except ET.ParseError:
                    raise f"Error parsing {template_path}"

                ea_path = f"{self.lookup_folder}EA_Info_{stage}.json"
                if not os.path.exists(ea_path):
                    raise ValueError(f"EA Info file not found: {ea_path}")
                with open(ea_path, "r") as ea:
                    ea_list = json.load(ea)
                if ea_list:
                    template_tree = update_ea_info(template_tree, ea_list)
                    out_folder = "../ea_info/"
                    os.makedirs(out_folder, exist_ok=True)
                    write_xml(template_tree, f"{out_folder}withEA_{stage}.xml")

                matching_rows = self.dfirm_lookup.loc[self.dfirm_lookup['HUC8'] == watershed]
                if matching_rows.empty:
                    continue
                DFIRM_ID = matching_rows['DFIRM_ID'].values[0]
                SOURCE_CIT = matching_rows['SOURCE_CIT'].values[0]
                print(f'\nTemplate: {template_path}\n{watershed}: {DFIRM_ID}, {SOURCE_CIT}')
                self.sources_lookup = fill_df_with_values(self.sources_lookup, ["DFIRM_ID", "SOURCE_CIT"],
                                                          **{"DFIRM_ID": DFIRM_ID, "SOURCE_CIT": SOURCE_CIT})

                place_tree = self.create_places_sub_xml(details, template_tree, **{"DFIRM ID": DFIRM_ID})
                print(f"Section: {ET.tostring(place_tree.getroot(), encoding='utf-8')}")
                out_folder = "../places/"
                out_xml = out_folder + f"{DFIRM_ID}_PLACES.xml"
                write_xml(place_tree, out_xml)

                sources_tree = self.create_sources_xml(**{"DFIRM ID": DFIRM_ID,
                                                          "SOURCE_CIT": SOURCE_CIT})

                extents_tree = self.create_extents_xml(watershed, "HUC8")
                out_folder = "../extents/"
                os.makedirs(out_folder, exist_ok=True)
                output_file = f"{out_folder}{DFIRM_ID}_EXTENTS.xml"
                write_xml(extents_tree, output_file)

                out_folder = "../source_cit/"
                os.makedirs(out_folder, exist_ok=True)
                output_file = f"{out_folder}{DFIRM_ID}_SOURCE_CIT.xml"
                write_xml(sources_tree, output_file)

                del template_tree


if __name__ == "__main__":
    fema_xml = CreateFEMAxml()
    fema_xml.create_fema_metadata()
