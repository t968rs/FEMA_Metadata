import sys
sys.path.append(r"E:\automation\toolboxes\gabelscience\src")
from d00_utils.bounds_convert import extent_excel_from_fc

fc = r"E:\Iowa_00_Tracking\01_statewide\Statewide_Info_FC.gdb\S_Submittal_Info_HUC8_03"

output_excel = "./_Extents_by_HYUC8.xlsx"
field_name = "HUC8"

outpath = extent_excel_from_fc(fc, field_name, output_excel)
print(f"Excel written to: {outpath}")