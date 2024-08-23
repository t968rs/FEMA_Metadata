import pandas as pd
import xml.etree.ElementTree as ET
from helpers import *
import os


def create_watershed_xml(watershed_lookup, template_tree, source_cit_tree, place_tree):
    # Create a deep copy of the root element
    new_root = ET.ElementTree(ET.fromstring(ET.tostring(template_tree.getroot())))

    # Find and remove the source_cit and place sections
    for elem in new_root.iter():
        for child in list(elem):
            if child.tag in ['srcinfo', 'place']:
                elem.remove(child)
    # write_xml(new_root, f"{watershed_lookup['DFIRM_ID']}_TEST_CLEARED.xml")

    # Get the srcinfo and place sections from the source_cit and place XML files
    source_cit_root = source_cit_tree.getroot()
    print(f"Source CIT: {source_cit_root.tag}")
    place_root = place_tree.getroot()
    print(f"Place: {place_root.tag}")

    # Find the lineage tag
    lineage = new_root.find('.//lineage')
    # Extract and append the srcinfo sections
    if lineage is not None:
        for i, srcinfo in enumerate(source_cit_root.findall(f'.//srcinfo')):
            print(f"Source {i}")
            # Insert srcinfo elements immediately after the start of the lineage tag
            lineage.insert(i, srcinfo)

    # Extract and append the place sections
    for place in place_root.findall('place'):
        new_root.getroot().append(place)

    # Save the new XML document
    new_tree = ET.ElementTree(new_root.getroot())
    outfolder = "../fulloutfullout/"
    outxml = f"{outfolder}{watershed_lookup['DFIRM_ID']}_DRAFT_metadata.xml"
    write_xml(new_tree, outxml)


def open_df_and_populate_xml(excel_path, xml_path):
    purchases_df = excel_to_df(excel_path, sheet_name="MIP Purchase Geographies")
    fips_lookup = excel_to_df(excel_path, sheet_name="FIPS Lookup")
    dfirm_lookup = excel_to_df(excel_path, sheet_name="Purchase CID Lookup")
    sources_lookup = excel_to_df(excel_path, sheet_name="SOURCE_CIT_STATEWIDE", dtype=str)
    print(sources_lookup['PUBLISHER'])
    unique_dates = list(
        set(sources_lookup['SRC_DATE'].dropna().unique()).union(set(sources_lookup['PUB_DATE'].dropna().unique())))

    # Read the base XML template
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Iterate through the watersheds DataFrame and create XML files
    for _, row in dfirm_lookup.iterrows():
        w_dict = row.to_dict()
        for k, v in w_dict.items():
            if pd.isna(v):
                w_dict[k] = None

        # If we haven't gotten a title, skip
        if 'MIP Purchase Name' not in w_dict or not w_dict['MIP Purchase Name']:
            continue
        print(w_dict)

        sources_path = f"../source_cit/{w_dict['DFIRM_ID']}_SOURCE_CIT.xml"
        places_path = f"../places/{w_dict['DFIRM_ID']}_PLACE_metadata.xml"
        if not os.path.exists(sources_path) or not os.path.exists(places_path):
            continue

        # Populate study-specific values (DFIRM_ID, SOURCE_CIT, etc.)
        this_source = sources_lookup[sources_lookup['SOURCE_CIT'].isnull() | (sources_lookup['SOURCE_CIT'] == 'nan')]
        other_sources = sources_lookup[~sources_lookup['SOURCE_CIT'].isnull() & (sources_lookup['SOURCE_CIT'] != 'nan')]
        if not this_source.empty:
            this_source.loc[:, 'SOURCE_CIT'] = row['SOURCE_CIT']
            print(f"\nStudy: {row['SOURCE_CIT']}")
            print(f'Source: {this_source["SOURCE_CIT"]})')
        else:
            print(f'No source for {row["SOURCE_CIT"]}')
        all_sources = pd.concat([this_source, other_sources], ignore_index=True)
        print(all_sources['SOURCE_CIT'].unique().tolist())
        all_sources['DFIRM_ID'] = row['DFIRM_ID']

        src_dict = all_sources.to_dict(orient='records')
        # print(f"Source dict: {src_dict}")

        # Get the date
        date = all_sources.loc[all_sources['SOURCE_CIT'] == w_dict['SOURCE_CIT'], 'SRC_DATE'].values[0]
        w_dict['pubdate'] = date

        source_cit_tree = ET.parse(sources_path)
        place_tree = ET.parse(places_path)
        create_watershed_xml(w_dict, tree, source_cit_tree, place_tree)


# Load the watersheds DataFrame
# Load the watersheds DataFrame
excelpath = "../Area_1A_Purchase_Geographies_ADDS.xlsx"
template_xml = "../AP20IA_DRAFT_metadata.xml"

open_df_and_populate_xml(excelpath, template_xml)



