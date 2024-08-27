from xml.dom import minidom
import pandas as pd
import os
import xml.etree.ElementTree as ET

TAG_KEYWORDS = {"srcinfo": ["STUDY", "BASE", "TOPO", "FIRM"]}


def excel_to_df(excel_file, sheet_name=None, **kwargs):
    df = pd.read_excel(excel_file, sheet_name)
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

    print(f"Missing Values:\n{missing_values_df}")

    # Update the missing values with the provided DFIRM_ID and SOURCE_CIT from kwargs
    print(f"KWARGS: {kwargs}")
    for c in fields_to_get:
        if c in df.columns:
            df.loc[missing_values_df[c], c] = kwargs.get(c)
    return df


def update_xml_from_dict(elem, d):
    for key, val in d.items():
        if isinstance(val, list):
            for item in val:
                sub_elem = ET.SubElement(elem, key)
                sub_elem.text = str(item)
        else:
            sub_elem = elem.find(f".//{key}")
            if sub_elem is not None:
                sub_elem.text = str(val)
            else:
                sub_elem = ET.SubElement(elem, key)
                sub_elem.text = str(val)


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


def add_parent_tag_to_tree(tree, new_parent_tag):
    # Get the root element of the tree
    root_element = tree.getroot()

    # Create a new parent element
    new_parent = ET.Element(new_parent_tag)

    # Set the existing tree's root as a child of the new parent element
    new_parent.append(root_element)

    # Create a new tree with the new parent as the root
    new_tree = ET.ElementTree(new_parent)

    return new_tree


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
    date_columns = [col for col in df.columns if "date" in col.lower()]
    for col in date_columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y%m%d')  # Convert datetime64 dtype to YYYYMMDD format
        elif pd.api.types.is_string_dtype(df[col]):
            try:
                df[col] = pd.to_datetime(df[col], format='%m/%d/%Y').dt.strftime(
                    '%Y%m%d')  # Convert string dates to YYYYMMDD format
            except ValueError:
                continue
        elif pd.api.types.is_datetime64_dtype(df[col]):
            df[col] = df[col].strftime('%Y%m%d')
    return df


def pretty_print_xml(xml_str):
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


def stack_xml(xml_str1, xml_str2):
    # Parse the XML strings
    root1 = ET.fromstring(xml_str1)
    root2 = ET.fromstring(xml_str2)

    # Create a new root element
    new_root = ET.Element("root")

    # Append the root elements of both XML files to the new root element
    new_root.append(root1)
    new_root.append(root2)

    # Convert the combined XML tree back to a string
    return ET.tostring(new_root, encoding='unicode')


# Function to overwrite or add elements
def overwrite_or_add(parent, element):
    existing = parent.find(element.tag)
    if existing is not None:
        parent.remove(existing)
    parent.append(element)


def write_xml(xml_tree, outpath):
    if os.path.exists(outpath):
        os.remove(outpath)

    xml_str = ET.tostring(xml_tree.getroot(), encoding='utf-8').decode('utf-8')
    xml_str = remove_extraneous_spacing(xml_str)
    xml_str = pretty_print_xml(xml_str)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(xml_str)
        print(f"Wrote {outpath}")
