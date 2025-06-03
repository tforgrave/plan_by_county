from urllib.request import urlopen
import json
with urlopen('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json') as response:
    counties = json.load(response)

import pandas as pd
import numpy as np
import dash

from dash import Dash, html, dcc

app = Dash(__name__)
server = app.server


# Read main data
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
import plotly.graph_objects as go

# Load state centers from JSON file
with open("state_names_and_coords.json", "r") as f:
    state_centers = json.load(f)

color_min = grouped["number_of_plans"].min()
color_max = grouped["number_of_plans"].max()

# Apply log scale to the color column (add 1 to avoid log(0))
grouped["log_number_of_plans"] = np.log10(grouped["number_of_plans"] + 1)

# fig = px.choropleth(
#     grouped,
#     geojson=counties,
#     locations='fips',  # Use the FIPS code as locations
#     color='log_number_of_plans',  # or whatever value you want to map
#     color_continuous_scale="Viridis",
#     range_color=(grouped["log_number_of_plans"].min(), grouped["log_number_of_plans"].max()),
#     scope="usa",
#     hover_data={"county name": True, "fips": False, "SF_TOT_PARTCP_BOY_CNT": True},
#     labels={'county name': 'county', 'log_number_of_plans': 'Number of Plans'}
# )

# Define ticks for the colorbar (log scale, but show actual values as labels)
log_min = grouped["log_number_of_plans"].min()
log_max = grouped["log_number_of_plans"].max()
# Choose a few "nice" ticks for the actual values
actual_ticks = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
log_ticks = np.log10(np.array(actual_ticks) + 1)
# Only keep ticks within your data's range
tickvals = [v for v in log_ticks if log_min <= v <= log_max]
ticktext = [str(int(v)) for v, lv in zip(actual_ticks, log_ticks) if log_min <= lv <= log_max]
# print(tickvals)
# print(ticktext)

choropleth = go.Choropleth(
    geojson=counties,
    locations=grouped['fips'],
    z=grouped['log_number_of_plans'],
    customdata=np.stack([grouped["county name"], grouped["number_of_plans"]], axis=-1),
    colorscale="Viridis",
    colorbar=dict(
        tickvals=tickvals,
        ticktext=ticktext,
        title="Number of Plans"
    ),
    hovertemplate="<b>County:</b> %{customdata[0]}<br><b>Plans:</b> %{customdata[1]}<extra></extra>",
    marker_line_width=0
)


fig = go.Figure(choropleth)



# fig.update_traces(
#     colorbar=dict(
#         tickvals=tickvals,
#         ticktext=ticktext,
#         title="Number of Plans"
#     ),
#     selector=dict(type='choropleth')
# )

# After creating your fig with px.choropleth and before app.layout:
choropleth_trace = None
for trace in fig.data:
    if trace.type == "choropleth":
        choropleth_trace = trace
        break


    
# Custom hovertemplate and hoverlabel styling
fig.update_traces(
    hovertemplate="<b>County:</b> %{customdata[0]}<br>" +
                  "<b>Plans:</b> %{customdata[1]}<extra></extra>",
    customdata=grouped[["county name", "number_of_plans"]],
    hoverlabel=dict(
        bgcolor="lightblue",
        font_size=12,
        font_family="Arial"
    )
)

if choropleth_trace:
    choropleth_trace.colorbar.tickvals = tickvals
    choropleth_trace.colorbar.ticktext = ticktext
    choropleth_trace.colorbar.title = "Number of Plans"

# Overlay state abbreviations at their coordinates
for state in state_centers:
    if "lat" in state and "lon" in state and "abbr" in state:
        fig.add_trace(go.Scattergeo(
            lon=[state["lon"]],
            lat=[state["lat"]],
            text=state["abbr"],
            mode='text',
            showlegend=False,
            textfont=dict(size=12, color="darkgrey", family="Arial")
        ))

fig.update_layout(
    geo=dict(
        scope="usa",
        projection=dict(type="albers usa"),
        showlakes=True,  # Optional: show lakes
        lakecolor="rgb(255, 255, 255)"  # Optional: lake color
    ),
    margin={"r":0,"t":0,"l":0,"b":0},
    height=800,  # You can adjust this value as needed
    width=None
)
print(choropleth_trace.colorbar)
fig.show()

# app.layout = html.Div(
#     style={"height": "100vh", "width": "100vw"},  # Full viewport
#     children=[
#         html.H1("Plans by County", style={"textAlign": "center", "marginTop": "20px"}),
#         dcc.Graph(
#             figure=fig,
#             style={"height": "90vh", "width": "100vw"}  # Make the map fill most of the screen
#         )
#     ]
# )