from xml.dom import minidom
import pandas as pd
import geopandas as gpd
import os
import numpy as np
import xml.etree.ElementTree as ET
from collections import defaultdict
import re

TAG_KEYWORDS = {"srcinfo": ["STUDY", "BASE", "TOPO", "FIRM"]}


def get_unique_values(df, field):
    return df[field].unique().tolist()

def shp_to_df(shp_file, **kwargs):
    gdf = gpd.read_file(shp_file, **kwargs)
    df = gdf.drop(columns="geometry")
    return df

def remove_empty_tags(tree: ET.ElementTree) -> ET.ElementTree:
    root = tree.getroot()

    # Function to recursively remove empty tags
    def remove_empty_elements(element):
        for child in list(element):
            if len(child) == 0 and (child.text is None or not child.text.strip()):
                element.remove(child)
            else:
                remove_empty_elements(child)

    # Remove empty elements
    remove_empty_elements(root)

    # Return the cleaned XML string
    return ET.tostring(root, encoding='unicode')


def remove_whitespace(text):
    # Remove all whitespace, tabs, and newlines
    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    cleaned_text = cleaned_text.replace("\n", " ").replace("\t", " ")
    cleaned_text = cleaned_text.strip()
    return cleaned_text


def find_repeated_elements(root):
    # Dictionary to count occurrences of each tag
    tag_count = defaultdict(int)

    # Traverse the tree and count tags
    def traverse(element):
        tag_count[element.tag] += 1
        for child in element:
            traverse(child)

    traverse(root)

    # Find tags that are repeated beyond their own closing tag
    repeated_tags = {tag: count for tag, count in tag_count.items() if count > 1}
    for tag, count in repeated_tags.items():
        print(f"Repeated tag '{tag}' {count} times")
    return repeated_tags


def re_root_elements(root, repeated_tags):
    def clean(element, parent=None):
        seen_tags = set()
        for child in list(element):
            if child.tag in repeated_tags:
                # print(f"{child.tag} is repeated")  # Debugging print
                #if child.tag in seen_tags:
                print(f"Re-rooting {child.tag}")  # Debugging print
                for grandchild in list(child):
                    element.append(grandchild)
                element.remove(child)
                #else:
                #seen_tags.add(child.tag)
                #clean(child, element)
            else:
                clean(child, element)

    clean(root)


def clean_metadata_tree(tree) -> ET.ElementTree:
    # Parse the XML file
    root = tree.getroot()

    # Ensure the root is "metadata"
    if root.tag != "metadata":
        raise ValueError("Root element is not 'metadata'")

    # Find repeated elements
    repeated_tags = find_repeated_elements(root)

    # Remove repeated elements
    re_root_elements(root, repeated_tags)

    return tree


def excel_to_df(excel_file, sheet_name=None, **kwargs):
    df = pd.read_excel(excel_file, sheet_name, dtype={"HUC8": str})
    df = convert_timestamps_to_strings(df)
    if "dtype" in kwargs:
        df = df.astype(kwargs['dtype'])
    return df


def fill_df_with_values(df, fields_to_get: list[str], **kwargs) -> dict:
    # Filter rows where DFIRM_ID or SOURCE_CIT are missing, null, or contain invalid values
    invalid_values = ["nan", "", " "]
    missing_values_df = pd.DataFrame(index=df.index)

    for c in fields_to_get:
        if c in df.columns:
            missing_values_df[c] = df[c].isnull() | df[c].isin(invalid_values)

    # print(f"Missing Values:\n{missing_values_df}")

    # Update the missing values with the provided DFIRM_ID and SOURCE_CIT from kwargs
    print(f"KWARGS: {kwargs}")
    for c in fields_to_get:
        if c in df.columns:
            df.loc[missing_values_df[c], c] = kwargs.get(c)
    return df


def extract_subtree_within_tag(tree, tag):
    root = tree.getroot()
    start_element = root.find(f".//{tag}")

    if start_element is None:
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

    # Create a new tree with the extracted elements
    new_root = ET.Element(parent.tag)
    for elem in extracted_elements:
        new_root.append(elem)

    return ET.ElementTree(new_root)


def extract_all_of_tag(xml_str, tag_str):
    # Function to determine if an element is valid based on the criteria
    def is_invalid_keywords(elem, **kwargs):
        all_strings = []
        for child in elem.iter():
            if child is not elem:
                if child.text and child.text.strip() != "False":
                    all_strings.append(child.text)
        valid_string = None
        any_valid = False
        if "wildcards" in kwargs:
            for wc in kwargs["wildcards"]:
                for string in all_strings:
                    if wc.lower() in string.lower():
                        any_valid = True
                        valid_string = string
        return any_valid, valid_string

    # Parse the XML string
    root = ET.fromstring(xml_str)

    # Find all <srcinfo> elements
    elems = root.findall(f".//{tag_str}")
    # Filter elements based on the criteria
    valid_elems, goodstrings = [], []
    for e in elems:
        valid_xml, goodstring = is_invalid_keywords(e, **{"wildcards": TAG_KEYWORDS[tag_str]})
        if valid_xml:
            valid_elems.append(e)
            goodstrings.append(goodstring)

    print(f"Valid: {len(valid_elems)}, {", ".join(goodstrings)}")

    # Convert each valid element back to a string
    return valid_elems


def convert_timestamps_to_strings(df):
    date_columns = [col for col in df.columns if "date" in col.lower() and "ref" not in col.lower()]
    # print(f'CNVRT  270, Found: {date_columns}')
    date_columns.extend(["SRC_DATE", "COMP_DATE", "PUB_DATE",])
    date_columns = list(set(date_columns))
    for col in date_columns:
        if col in df.columns:
            # df[col] = df[col].astype(str)
            print(f"\tCNVRT 195: {col}: {df[col].values}")
            try:
                # Attempt to convert the column to datetime
                df[col] = pd.to_datetime(df[col], errors='coerce')
                # Convert datetime to the desired format
                df[col] = df[col].dt.strftime('%Y%m%d')
                print(f"\t\tConverted {col}: {df[col].values}")
                unique_dates = df[col].unique().tolist()
                # print(f"Unique {col} values: {unique_dates}")
            except Exception as e:
                # If conversion fails, print the error and continue
                print(f"Could not convert column {col}: {e}")

    return df


def pretty_print_xml(xml_str) -> str:
    dom = minidom.parseString(xml_str)
    return dom.toprettyxml(indent="  ")


def remove_extraneous_spacing(xml_str):
    # Parse the XML string
    dom = minidom.parseString(xml_str)

    # Function to recursively remove empty text nodes
    def remove_empty_text_nodes(node):
        to_remove = []
        for child in node.childNodes:
            if child.nodeType == minidom.Node.TEXT_NODE and not child.data.strip():
                to_remove.append(child)
            elif child.hasChildNodes():
                remove_empty_text_nodes(child)
        for child in to_remove:
            node.removeChild(child)

    # Remove empty text nodes from the document
    remove_empty_text_nodes(dom)

    # Return the cleaned XML string
    return dom.toxml()


def write_xml(xml_tree, outpath):
    if os.path.exists(outpath):
        os.remove(outpath)

    xml_str = ET.tostring(xml_tree.getroot(), encoding='utf-8').decode('utf-8')
    xml_str = remove_extraneous_spacing(xml_str)
    xml_str = pretty_print_xml(xml_str)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(xml_str)
        # print(f"Wrote {outpath}")
