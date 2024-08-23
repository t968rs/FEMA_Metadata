import json
import os
import xml.etree.ElementTree as ET
import xmltodict
import typing as T
from pprint import pprint as pprint
from xml.dom import minidom

TAG_FORMAT = {
    "metadata": {"idinfo": {}, "dataqual": {}, "spref": {}, "ea_info": {}, "distinfo": {}, "metainfo": {}}
}


def json_to_dict(json_file):
    with open(json_file, "r") as f:
        data = json.load(f)
    return data


def get_parents(dictionary):
    parents_only = {k: v for k, v in dictionary.items() if v}
    content_only = {k: v for k, v in dictionary.items() if not v}
    root_tag_str = "metadata"

    unique_parents = set(root_tag_str)
    for umbrella, sub_dict in TAG_FORMAT["metadata"].items():

        for k, v in dictionary.items():
            if umbrella in k:
                rel = os.path.relpath(k, umbrella)
                normed = os.path.normpath(rel)
                unique_parents.add(normed)

    nested_parents = {k: v for k, v in TAG_FORMAT.items()}
    for parent_path in list(unique_parents):
        first_part = parent_path.split('/')[0]
        nested_tags = nested_parents.get(first_part)
        for part in parent_path.split('/')[1:]:
            if part not in nested_tags:
                nested_tags[part] = {}
                nested_parents[first_part] = nested_tags

    return unique_parents


def generate_xml_from_dict(root_tag="metadata", data_dict=None) -> str:
    if data_dict is None:
        data_dict = {}
    if not isinstance(data_dict, dict):
        raise ValueError("data_dict must be a dictionary")
    if root_tag not in data_dict or not isinstance(data_dict[root_tag], dict):
        raise ValueError(f"data_dict must contain a dictionary under the key '{root_tag}'")
    root = dict_to_xml(root_tag, data_dict[root_tag])
    return ET.tostring(root, encoding='unicode')


def dict_to_xml(tag, d):
    if not isinstance(d, dict):
        raise ValueError("Expected a dictionary")
    elem = ET.Element(tag)
    for key, val in d.items():
        child = ET.Element(key)
        if isinstance(val, dict):
            child.append(dict_to_xml(key, val))
        else:
            child.text = str(val)
        elem.append(child)
    return elem


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


def write_xml(xml_tree, output_file):
    if os.path.exists(output_file):
        os.remove(output_file)

    xml_str = ET.tostring(xml_tree.getroot(), encoding='utf-8').decode('utf-8')
    xml_str = remove_extraneous_spacing(xml_str)
    xml_str = pretty_print_xml(xml_str)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xml_str)


def generate_nested_dict(dict_unique_keys, order_lookup=None):
    # Sort keys based on order_lookup
    sorted_keys = sorted(dict_unique_keys.keys(), key=lambda k: order_lookup.get(k, float('inf')),
                         reverse=False)

    nested_keys = {}
    for key in sorted_keys:
        value = dict_unique_keys[key]
        key_parts = key.split('/')
        d = nested_keys
        for k in key_parts[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]

        if isinstance(d, dict):
            d[key_parts[-1]] = value if isinstance(value, T.Union[bool, str]) else {}
        else:
            raise TypeError(f"Expected a dictionary at {key_parts[:-1]}, but found {type(d)}")
    return nested_keys


order_dict = json_to_dict("../regen_lookups/ORDER_unnested.json")
for stage in ["Hydraulics", "DRAFT"]:
    json_path = f'../regen_lookups/post_KDP_{stage}_unnested.json'
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"File not found: {json_path}")
    post_kdp = json_to_dict(json_path)
    nested_kdp = generate_nested_dict(post_kdp, order_dict)

    # Write the dictionary to json
    post_kdp_path = f'../regen_lookups/post_kdp_{stage}_nested.json'
    with open(post_kdp_path, "w") as f:
        json.dump(nested_kdp, f, indent=3)

    # Convert dictionary to xml
    xml_string = generate_xml_from_dict(data_dict=nested_kdp)
    xml = ET.ElementTree(ET.fromstring(xml_string))

    # Write the xml to file
    outpath = f"../regen_lookups/post_kdp_{stage}.xml"
    write_xml(xml, outpath)
