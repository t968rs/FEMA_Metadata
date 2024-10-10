import pandas as pd
import os
from helpers import excel_to_df
import logging
import numpy as np

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


def fill_source_cit_each_proj(template, proj_lookup_df,
                              source_queries=None):
    if source_queries is None:
        source_queries = {"AUTHOR": "AtkinsRealis",
                             "SOURCE_CIT": None}
    template_row = pd.DataFrame(columns=template.columns)
    template_row_len = 10
    while template_row_len != 1:
        for i, (col, value) in enumerate(source_queries):
            if col in template.columns:
                if i == 0:
                    if value is not None:
                        template_row = template.loc[(template[col] == value)]
                    else:
                        template_row = template
    template_row = template_row.drop(columns=['SOURCE_CIT', 'DFIRM_ID'])
    logger.debug(f"Template Row: {template_row}")
    print(f"Authors: {self.sources_lookup['AUTHOR'].tolist()}")
    print(f"Author: {self.author}")
    dfirm_dict = self.dfirm_lookup.to_dict(orient='index')
    print(f"DFIRM Dict: {len(dfirm_dict)}")

    date_cols = ['PUB_DATE', 'SRC_DATE', "COMP_DATE"]
    for col in date_cols:
        if col in self.sources_lookup.columns:
            unique_dates = self.sources_lookup[col].unique().tolist()
            print(f"{col}: {unique_dates}, {self.sources_lookup[col].dtype}")
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

        # Append the new row to new_rows using pd.concat
        new_rows = pd.concat([new_rows, new_row], ignore_index=True)

    other_rows = self.sources_lookup.loc[(self.sources_lookup['AUTHOR'] != self.author) |
                                         (~self.sources_lookup['SOURCE_CIT'].str.contains("STUDY") &
                                          pd.notna(self.sources_lookup['SOURCE_CIT']) &
                                          (self.sources_lookup['SOURCE_CIT'] != 'nan'))]
    other_rows["DFIRM_ID"] = np.nan
    print(f"Other Rows: {other_rows['SOURCE_CIT'].tolist()}\n")
    all_rows = pd.concat([new_rows, other_rows], ignore_index=True)
    print(f"All Rows: {all_rows['SOURCE_CIT'].tolist()}\n")
    return all_rows

if __name__ == "__main__":
    excel_path = "../Area_1A_Purchase_Geographies_ADDS.xlsx"
    source_cit_template_sheet = "SOURCE_CIT_STATEWIDE"
    lookup_sheet = "Purchase CID Lookup"

    # Read the lookup sheet
    lookup_df = excel_to_df(excel_path, sheet_name=lookup_sheet)
    template_df = excel_to_df(excel_path, sheet_name=source_cit_template_sheet)