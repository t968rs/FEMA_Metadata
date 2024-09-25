import xml.etree.ElementTree as ET
import json


def parse_xml_to_dict(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    tabs_lookup = {}

    def traverse(node, parent_path, level):
        tag = node.tag
        if tag not in tabs_lookup:
            tabs_lookup[f"{parent_path}/{tag}"] = level

        for child in node:
            traverse(child, f"{parent_path}/{tag}", level + 1)

    traverse(root, "", 0)
    return tabs_lookup


def parse_xml_and_identify_tags(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    tags_only = {}

    def traverse(node, parent_path):
        tag = node.tag
        path = f"{parent_path}/{tag}" if parent_path else tag

        # Check if the node contains only other tags
        contains_only_tags = all(child.tag for child in node) and not node.text.strip()

        tags_only[path] = contains_only_tags

        for child in node:
            traverse(child, path)

    traverse(root, "")
    return tags_only


def parse_eainfo(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    eainfo_list = []

    for detailed in root.findall(".//detailed"):
        enttyp = detailed.find("enttyp")
        if enttyp is not None:
            enttypl = enttyp.find("enttypl").text if enttyp.find("enttypl") is not None else None
            enttypd = enttyp.find("enttypd").text if enttyp.find("enttypd") is not None else None
            enttypds = enttyp.find("enttypds").text if enttyp.find("enttypds") is not None else None
            eainfo_list.append({
                "enttypl": enttypl,
                "enttypd": enttypd,
                "enttypds": enttypds
            })

    for overview in root.findall(".//overview"):
        eaover = overview.find("eaover").text if overview.find("eaover") is not None else None
        eadetcit_list = [eadetcit.text for eadetcit in overview.findall("eadetcit")]
        eainfo_list.append({
            "eaover": eaover,
            "eadetcit": eadetcit_list
        })

    return eainfo_list


xml_path = "../static_lookups/000000_Terrain_metadata.xml"
tag_dict = parse_xml_to_dict(xml_path)
tag_tf = parse_xml_and_identify_tags(xml_path)
ea_info = parse_eainfo(xml_path)

# Output:
task_type = xml_path.split("/")[-1].split("_")[1].split("_")[0]
with open(f"../regen_lookups/TAB_lookup_{task_type}_metadata.json", "w") as f:
    json.dump(tag_dict, f, indent=0)
with open(f"../regen_lookups/TAGS_TF_{task_type}_metadata.json", "w") as f:
    json.dump(tag_tf, f, indent=0)

with open(f"../regen_lookups/Tags_withValues_{task_type}_metadata.json", "w") as f:
    json.dump({k: v for k, v in tag_tf.items() if not v}, f, indent=0)

with open(f"../regen_lookups/EA_Info_{task_type}_metadata.json", "w") as f:
    json.dump(ea_info, f, indent=0)
