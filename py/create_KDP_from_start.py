import json
import re
from pprint import pprint


def json_to_dict(path):
    # Create dict from json file
    with open(path, "r") as f:
        data = json.load(f)
    return data


def create_key_order_lookup(dictionary):
    # Create a dictionary with the keys as the order of the keys in the dictionary
    key_order = {}
    for i, key in enumerate(dictionary.keys()):
        key_order[key] = i
    return key_order


def strip_extra_spaces(input_string):
    # Replace multiple spaces, tabs, and newlines with a single space
    cleaned_string = re.sub(r'\s+', ' ', input_string)

    # Strip leading and trailing spaces and special characters
    cleaned_string = re.sub(r'^[\s\"\'\\]+|[\s\"\'\\]+$', '', cleaned_string)

    # Strip escape characters and ellipses
    bad_char = ['\\' '..', '...', '/', '"']
    for char in bad_char:
        cleaned_string = cleaned_string.replace(char, '')

    # Replace multiple spaces, tabs, and newlines with a single space
    cleaned_string = cleaned_string.replace('  ', ' ')

    return cleaned_string


def traverse_nested_dict(nested_dict):
    def traverse(d, parent_key=''):
        for key, value in d.items():
            full_key = f"{parent_key}/{key}" if parent_key else key
            if isinstance(value, dict):
                traverse(value, full_key)
            else:
                print(f"Key: {full_key}\nValue: {value}\n")
                if len(value) > 20:
                    new_value = strip_extra_spaces(value)
                    nested_dict[full_key] = new_value
                    print(f"Key: {full_key}\nValue: {new_value}\n")

    traverse(nested_dict)
    return nested_dict


def merge_dicts(dict1, dict2):
    merged = {}

    # Step 3: Iterate over the keys of dict1 to preserve the order
    for key in dict1.keys():
        value1 = dict1.get(key)
        value2 = dict2.get(key)

        if value1 is not None:
            merged[key] = value1
        elif value2 is not None:
            merged[key] = value2
        else:
            merged[key] = None

    # Step 7: Add any remaining keys from dict2 that are not in dict1
    for key, value in dict2.items():
        if value not in [False, None] and dict1.get(key) in [False, None]:
            merged[key] = dict2.get(key)

    new_dict = {k: v for k, v in merged.items()}
    for key, value in merged.items():
        # print(f"Key: {key}\nValue: {value}\n")
        if isinstance(value, str):
            if len(value) > 160:
                print(f"Key: {key}\nValue: {value}\n")
                new_value = strip_extra_spaces(value)
                new_dict[key] = new_value
                print(f"New Value: {new_value}\n")
    return new_dict


tag_tf = json_to_dict("../regen_lookups/TAGS_TF_Terrain_metadata.json")
start_dict = json_to_dict("../static_lookups/xml_start_dict.json")
order_lookup = create_key_order_lookup(tag_tf)
with open(f"../regen_lookups/ORDER_unnested.json", "w") as f:
    json.dump(order_lookup, f, indent=0)

stage_dicts = json_to_dict("../static_lookups/KDP_Stages.json")

for stage, stage_dict in stage_dicts.items():
    post_kdp_dict = merge_dicts(start_dict, stage_dict)
    order_lookup = create_key_order_lookup(start_dict)
    # pprint(post_kdp_dict)
    with open(f"../regen_lookups/post_KDP_{stage}_unnested.json", "w") as f:
        json.dump(post_kdp_dict, f, indent=2)
