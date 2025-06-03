from urllib.request import urlopen
import json
with urlopen('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json') as response:
    counties = json.load(response)

import pandas as pd

import dash

from dash import Dash

app = Dash(__name__)
server = app.server

# Read your main data
# df = pd.read_csv("sample_zip.csv", dtype={"zip": str})
df = pd.read_csv("F_5500_sf_2023_latest_prunned.csv", dtype={"SF_SPONS_US_ZIP": str})

# Ensure zip codes are exactly 5 digits (pad with zeros if needed)
# df["SF_SPONS_US_ZIP"] = pd.to_numeric(df["SF_SPONS_US_ZIP"], errors="coerce").dropna().astype(int).astype(str).str.zfill(5)
df["SF_SPONS_US_ZIP"] = df["SF_SPONS_US_ZIP"].str[:5].str.zfill(5)
# print(df["SF_SPONS_US_ZIP"].head())

# Read the HUD ZIP-to-county crosswalk. Contains ZIP codes, FIPS codes (called "geoid"), and a resolution ratio.
crosswalk = pd.read_csv("hud_zip_crosswalk.csv", dtype={"zip": str, "geoid": str})

# Keep only the zip code row with the highest res_ratio (most people live in that county)
crosswalk = crosswalk.sort_values("res_ratio", ascending=False).drop_duplicates(subset=["zip"], keep="first")

# Merge on main data with the data from the crosswalk (this will add the geoid column)
merged = pd.merge(df, crosswalk, left_on="SF_SPONS_US_ZIP", right_on="zip", how="left")

# If the geoid code is not 5 digits, pad with zeros, then create a new column "fips" with the padded geoid
merged["fips"] = merged["geoid"].str.zfill(5)
# merged.to_csv("merged_zip_crosswalk_data.csv", index=False)
# print(merged.head())

# Read the FIPS to county name mapping
fips_to_county_names = pd.read_csv("fips_county_names.csv", dtype={"fips": str})

# Merge to get county names (at this point geoids are the same as fips codes)
# There should only be one Fips code per county, so this will not create duplicates
# merged = pd.merge(merged, fips_to_county_names, left_on="fips", right_on="fips", how="left")
# Save merged data to CSV
# merged.to_csv("merged_zip_county_data.csv", index=False)

# Group by county name, summing the 'SF_TOT_PARTCP_BOY_CNT' column
# This only leave the fips and sf_tot_partcp_boy_cnt columns
grouped = merged.groupby('fips', as_index=False).agg(
    SF_TOT_PARTCP_BOY_CNT=('SF_TOT_PARTCP_BOY_CNT', 'sum'),
    number_of_plans=('SF_TOT_PARTCP_BOY_CNT', 'count')
)
# grouped.to_csv("grouped_zip_county_data.csv", index=False)

# Add the county name to the grouped data
grouped = pd.merge(grouped, fips_to_county_names, left_on="fips", right_on="fips", how="left")
# grouped.to_csv("grouped_zip_county_data_with_county_names.csv", index=False)
# print(grouped.head())

# print(grouped.head())
import plotly.express as px

color_min = grouped["number_of_plans"].min()
color_max = grouped["number_of_plans"].max()

fig = px.choropleth(
    grouped,
    geojson=counties,
    locations='fips',  # Use the FIPS code as locations
    color='number_of_plans',  # or whatever value you want to map
    color_continuous_scale="Viridis",
    range_color=(color_min, color_max),
    scope="usa",
    hover_data={"county name": True, "fips": False, "SF_TOT_PARTCP_BOY_CNT": True},
    labels={'county name': 'county'}
)

# Custom hovertemplate and hoverlabel styling
fig.update_traces(
    hovertemplate="<b>County:</b> %{customdata[0]}<br>" +
                  "<b>Plans:</b> %{z}<extra></extra>",
    customdata=grouped[["county name"]],
    hoverlabel=dict(
        bgcolor="lightblue",
        font_size=12,
        font_family="Arial"
    )
)

fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
fig.show()