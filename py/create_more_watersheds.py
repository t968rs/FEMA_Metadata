import pandas as pd
import xml.etree.ElementTree as ET
from helpers import *
import os


def create_watershed_xml(tree, source_cit_tree, place_tree, extent_tree=None, ea_tree=None, crs_tree=None):
    # Create a new XML document from the template
    root = tree.getroot()

    # Get the srcinfo and place sections from the source_cit, place, and extent XML files
    source_cit_root = source_cit_tree.getroot()
    print(f"Source CIT: {source_cit_root.tag}")
    place_root = place_tree.getroot()
    print(f"Place: {place_root.tag}")

    # Extent insertion
    if extent_tree is not None:
        extent_root = extent_tree.getroot()
        spdom_elem = root.find('.//spdom')
        if spdom_elem is not None:
            for child in spdom_elem:
                spdom_elem.remove(child)
        else:
            raise ValueError("No spdom element found in the template XML")

        bounding = ET.SubElement(spdom_elem, 'bounding')
        for coord in extent_root.iter():
            print(f"Coord: {coord.text}")
            # Create a new child element with the tag name equal to coord.tag
            new_child = ET.SubElement(bounding, coord.tag)
            new_child.text = coord.text

    # Find the lineage tag
    lineage = root.find('.//lineage')
    # Extract and append the srcinfo sections
    if lineage is None:
        dataqual = root.find('.//dataqual')
        lineage = ET.SubElement(dataqual, 'lineage')
    source_count = 0
    for i, srcinfo in enumerate(source_cit_root.findall(f'.//srcinfo')):
        print(f"Source {i}")
        # Insert srcinfo elements immediately after the start of the lineage tag
        lineage.insert(i, srcinfo)
        source_count += 1
    procstep = source_cit_root.find('.//procstep')
    existing_procstep = lineage.find('.//procstep')
    if existing_procstep is not None:
        lineage.remove(existing_procstep)
    lineage.insert(source_count + 1, procstep)

    # Extract and append the place sections
    keywords = root.find('.//keywords')
    keywords.append(place_root)

    # Extract and append the ea_info sections
    if ea_tree is not None:
        eainfo_existing = root.find('.//eainfo')
        parent = root.find('.//eainfo/..')
        index = list(parent).index(eainfo_existing)
        parent.remove(eainfo_existing)

        # Insert EA Info at index
        ea_root = ea_tree.getroot()
        parent.insert(index, ea_root)

    # Extract and append the crs sections
    if crs_tree is not None:
        horizsys = root.find('.//horizsys')
        if horizsys is not None:
            parent = root.find('.//horizsys/..')
            index = list(parent).index(horizsys)
            parent.remove(horizsys)
            horizsys = ET.Element('horizsys')
            parent.insert(index, horizsys)
        horizsys = root.find('.//horizsys')
        crs_root = crs_tree.getroot()
        planar = crs_root.find('.//planar')
        geodetic = crs_root.find('.//geodetic')
        horizsys.append(planar)
        horizsys.append(geodetic)

    # Remove empty tags
    remove_empty_tags(tree)
    print(f"Type: {type(tree)}")
    return tree


def open_df_and_populate_xml(excel_path, xml_path, output_loc):
    dfirm_lookup = excel_to_df(excel_path, sheet_name="Purchase CID Lookup")
    sources_lookup = excel_to_df(excel_path, sheet_name="SOURCE_CIT_STATEWIDE", dtype=str)
    epsg_lookup = excel_to_df(excel_path, sheet_name="HUC8_Extents_SPCS", dtype=str)
    mip_purchase_geos = excel_to_df(excel_path, sheet_name="MIP Purchase Geographies", dtype=str)

    print(sources_lookup['PUBLISHER'])
    # Read the base XML template
    template_tree = ET.parse(xml_path)
    type_stage = "DRAFT" if "DRAFT" in xml_path else "Hydraulics"
    if "Floodplain" in xml_path:
        type_stage = "Floodplain"

    # Iterate through the watersheds DataFrame and create XML files
    # Create watershed dictionary from the DataFrame
    # Record CID and DFIRM relationships
    dfirm_cid_relationship = {}
    for _, row in dfirm_lookup.iterrows():
        # Create a deep copy of the root element
        new_tree = ET.ElementTree(ET.fromstring(ET.tostring(template_tree.getroot())))
        new_root = new_tree.getroot()

        # Find and remove the source_cit and place sections
        for elem in new_root.iter():
            for child in list(elem):
                if child.tag in ['srcinfo', 'place']:
                    elem.remove(child)

        w_dict = row.to_dict()
        for k, v in w_dict.items():
            if pd.isna(v):
                w_dict[k] = None

        # If we haven't gotten a title, skip
        if 'CASE_DESC' not in w_dict or not w_dict['CASE_DESC']:
            continue
        print(w_dict)

        ea_path = f"../ea_info/EA.xml"
        huc_code = w_dict["HUC8"]
        print(f"HUC8: {huc_code}")
        this_epsg_df = epsg_lookup[epsg_lookup['HUC8'] == huc_code]
        print(f"EPSG Lookup: {this_epsg_df}")
        epsg_huc8 = this_epsg_df['crs'].values[0]
        print(f"HUC8: {huc_code}, EPSG: {epsg_huc8}")

        # Define XML paths
        crs_path = f"../spcs/{epsg_huc8}_SPCS.xml"
        sources_path = f"../source_cit/{w_dict['DFIRM_ID']}_SOURCE_CIT.xml"
        places_path = f"../places/{w_dict['DFIRM_ID']}_PLACES.xml"
        extents_path = f"../extents/{w_dict['DFIRM_ID']}_EXTENTS.xml"

        if (not os.path.exists(sources_path) or not os.path.exists(places_path) or
                not os.path.exists(extents_path) or not os.path.exists(ea_path)):
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
        all_sources['DFIRM_ID'] = row['DFIRM_ID']

        # Get the date
        date = all_sources.loc[all_sources['SOURCE_CIT'] == w_dict['SOURCE_CIT'], 'SRC_DATE'].values[0]
        w_dict['pubdate'] = date

        # Insert project-specific values into the XML
        # Insert the title and pubdate
        citation = new_root.find('.//citation')
        cit_section = citation.find('.//citeinfo')
        if cit_section is not None:
            origin = cit_section.find('.//origin')
            if origin is not None:
                origin.text = w_dict["SUBMIT_BY"]
            title = cit_section.find('.//title')
            if title is not None:
                title.text = w_dict["CASE_DESC"]
            pubdate = cit_section.find('.//pubdate')
            if pubdate is not None:
                pubdate.text = w_dict["pubdate"]
            edition = cit_section.find('.//edition')
            if edition is not None:
                edition.text = "2.8.5.6"
        else:
            raise ValueError("No citation section found in the template XML")

        # LWORKS Section
        lworks = new_root.find('.//lworkcit')
        if lworks is not None:
            title = lworks.find('.//title')
            if title is not None:
                title.text = f'FEMA CASE {w_dict["CASE_NO"]}'
            pubdate = lworks.find('.//pubdate')
            if pubdate is not None:
                pubdate.text = w_dict["pubdate"]

        # Crossref section
        crossref = new_root.find('.//crossref')
        if crossref:
            origin = crossref.find('.//origin')
            origin.text = w_dict["SUBMIT_BY"]
            title = crossref.find('.//title')
            title.text = w_dict["CASE_DESC"]
            pubdate = crossref.find('.//pubdate')
            pubdate.text = w_dict["pubdate"]

        # Update the metad info section
        metainfo = new_root.find('.//metainfo')
        metad = metainfo.find('.//metd')
        metad.text = w_dict["pubdate"]

        # Update the metstdn section
        # metextns = new_root.find('.//metextns')

        # Update time period section
        timeperd = new_root.find('.//timeperd')
        caldate = timeperd.find('.//caldate')
        caldate.text = w_dict["pubdate"]

        # Insert the source_cit and place sections
        source_cit_tree = ET.parse(sources_path)
        place_tree = ET.parse(places_path)
        extent_tree = ET.parse(extents_path)
        ea_tree = ET.parse(ea_path)
        if type_stage != "DRAFT":
            crs_tree = ET.parse(crs_path)
            new_tree = create_watershed_xml(new_tree, source_cit_tree, place_tree, extent_tree, ea_tree, crs_tree)
        else:
            new_tree = create_watershed_xml(new_tree, source_cit_tree, place_tree, extent_tree, ea_tree)
        new_root = new_tree.getroot()
        for elem in new_root.iter():
            for child in list(elem):
                if child.text:
                    if "/n" in child.text:
                        print(f"Found newline in {child.tag}")
                    new_text = remove_whitespace(child.text)
                    child.text = new_text

        # Write the new XML file

        # Write the new XML file
        outfolder = f"{output_loc}{type_stage}/"
        os.makedirs(outfolder, exist_ok=True)
        if type_stage == "DRAFT":
            outxml = f"{outfolder}{w_dict['DFIRM_ID']}_DRAFT_metadata.xml"
        else:
            outsubfolder = f"{outfolder}{w_dict["DFIRM_ID"]}/"
            os.makedirs(outsubfolder, exist_ok=True)
            all_cid = mip_purchase_geos.loc[mip_purchase_geos['HUC8'] == huc_code, 'CID'].values
            first_cid = all_cid[0]
            if w_dict["DFIRM_ID"] in all_cid:
                this_cid = w_dict["DFIRM_ID"]
            else:
                this_cid = first_cid
            print(f"DFIRM, CID: {w_dict['DFIRM_ID']}, {this_cid}")
            if w_dict["DFIRM_ID"] not in dfirm_cid_relationship:
                dfirm_cid_relationship[w_dict["DFIRM_ID"]] = this_cid

            outxml = f"{outsubfolder}{this_cid}_{type_stage}_metadata.xml"
        write_xml(new_tree, outxml)
        print(f" Saved {outxml}")

    # Output CID and DFIRM relationships
    print(f"\n Stage: {type_stage}")
    if len(dfirm_cid_relationship) > 1:
        print(f"Dict CIDs: {dfirm_cid_relationship}")
        df_cid_dfirm = pd.DataFrame.from_dict(dfirm_cid_relationship, orient='index', columns=["CID"])
        print(f"DF: {df_cid_dfirm}")
        outfolder = f"{output_loc}{type_stage}/"
        os.makedirs(outfolder, exist_ok=True)
        df_cid_dfirm.to_excel(f"{outfolder}CID_DFIRM_relationships.xlsx",
                              columns=["CID"], index_label="DFIRM_ID")


# Load the watersheds DataFrame
excelpath = "../NE_Metadata_Tables.xlsx"
output_folder = "../NE_Pilot_BLE/"

for kdp in ["DRAFT", "Hydraulics", "Floodplain"]:
    template_xml = f"../static_lookups/_{kdp}_metadata.xml"
    open_df_and_populate_xml(excelpath, template_xml, output_folder)
