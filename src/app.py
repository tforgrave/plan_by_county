from urllib.request import urlopen
import json
import pandas as pd
import numpy as np
import dash
from dash import Dash, html, dcc, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go

app = Dash(__name__)
# app = Dash()
server = app.server

##############################################
# Read in all the data first
##############################################
# Load GeoJSON data for US counties
with urlopen('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json') as response:
    counties = json.load(response)

# Read main data
df = pd.read_csv("F_5500_sf_2023_latest_prunned.csv", dtype={"SF_SPONS_US_ZIP": str})

# Ensure zip codes are exactly 5 digits (pad with zeros if needed)
df["SF_SPONS_US_ZIP"] = df["SF_SPONS_US_ZIP"].str[:5].str.zfill(5)

# Read the HUD ZIP-to-county crosswalk. Contains ZIP codes, FIPS codes (called "geoid"), and a resolution ratio.
crosswalk = pd.read_csv("hud_zip_crosswalk.csv", dtype={"zip": str, "geoid": str})

# Keep only the zip code row with the highest res_ratio (most people live in that county)
crosswalk = crosswalk.sort_values("res_ratio", ascending=False).drop_duplicates(subset=["zip"], keep="first")

# Read the FIPS to county name mapping csv file
fips_to_county_names = pd.read_csv("fips_county_names.csv", dtype={"fips": str})

# Read the CSV and get unique Main Industry names and their main_code
business_codes = pd.read_csv("business_codes.csv")
main_industry_pairs = (
    business_codes[["Main_Industry", "Main_code"]]
    .drop_duplicates()
    .dropna(subset=["Main_Industry", "Main_code"])
    .sort_values("Main_Industry")
    .values
)

# Load state centers from JSON file
with open("state_names_and_coords.json", "r") as f:
    state_centers = json.load(f)
##############################################



# This callback will be triggered by changes to relayoutData 
# and will store the relevant geo keys in pan-zoom-store
@app.callback(
    Output("pan-zoom-store", "data"),
    Input("county-map", "relayoutData"),
    State("pan-zoom-store", "data"),
    prevent_initial_call=True
)
def pan_zoom_pos(relayout_data, stored_data):
    if not relayout_data:
        return dash.no_update
    # Start with the previous state, or empty dict
    new_state = dict(stored_data) if stored_data else {}
    for k, v in relayout_data.items():
        if k.startswith("geo.") and not isinstance(v, dict):
            subkey = k.split(".", 1)[1]
            new_state[subkey] = v
        elif k.startswith("geo.") and isinstance(v, dict):
            subkey = k.split(".", 1)[1]
            new_state[subkey] = v
    if new_state:
        print("Pan/Zoom Data Updated:", new_state)
        return new_state
    return dash.no_update


@app.callback(
    Output("county-map", "figure"),
    Input("industry-dropdown", "value"),
    State("pan-zoom-store", "data"),
    prevent_initial_call=True
)
def update_map(selected_codes, pan_zoom_data):
    print("update_map called with selected_codes:", selected_codes)
    # print("Selected code names and values:")
    # for code in selected_codes or []:
    #     # Find the industry name for this code (matching first two digits)
    #     prefix = str(code)[:2]
    #     matches = business_codes[business_codes["Main_code"].astype(str).str[:2] == prefix]
    #     name = matches["Main_Industry"].iloc[0] if not matches.empty else "Unknown"
    #     print(f"  {name}: {code}")
   


    ######################
    # Data Processing
    ######################

    # Filter df by SF_BUSINESS_CODE if selected_codes is provided
    if selected_codes:
        # Only consider the first two digits for comparison
        selected_prefixes = [str(code)[:2] for code in selected_codes]
        df_filtered = df[df["SF_BUSINESS_CODE"].astype(str).str[:2].isin(selected_prefixes)]
    else:
        df_filtered = df

    # Merge main data (df) with the data from ZIP-to-county (crosswalk)
    # The "geoid" column from ZIP-to-county will now be in the main data
    merged = pd.merge(df_filtered, crosswalk, left_on="SF_SPONS_US_ZIP", right_on="zip", how="left")

    # If the geoid code is not 5 digits, pad with zeros, then create a new column "fips" with the padded geoid
    merged["fips"] = merged["geoid"].str.zfill(5)

    # Group by county name (using fips id), counting the number of plans in each county
    # This only leave the fips and number_of_plans columns
    grouped = merged.groupby('fips', as_index=False).agg(
        number_of_plans=('fips', 'count')
    )

    # Add the county name to the grouped data
    grouped = pd.merge(grouped, fips_to_county_names, left_on="fips", right_on="fips", how="left")
    #####################

    # Get min and max values for the number of plans
    color_min = grouped["number_of_plans"].min()
    color_max = grouped["number_of_plans"].max()

    # Apply log scale to the color column (add 1 to avoid log(0))
    grouped["log_number_of_plans"] = np.log10(grouped["number_of_plans"] + 1)

    # Define ticks for the colorbar (log scale, but show actual values as labels)
    log_min = grouped["log_number_of_plans"].min()
    log_max = grouped["log_number_of_plans"].max()

    # Choose a few "nice" ticks for the actual values
    actual_ticks = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
    log_ticks = np.log10(np.array(actual_ticks) + 1)

    # Only keep ticks within your data's range
    tickvals = [v for v in log_ticks if log_min <= v <= log_max]
    ticktext = [str(int(v)) for v, lv in zip(actual_ticks, log_ticks) if log_min <= lv <= log_max]

    # Create the choropleth with filtered data
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
    fig_filtered = go.Figure(choropleth)

    # Overlay state abbreviations at their coordinates
    for state in state_centers:
        if "lat" in state and "lon" in state and "abbr" in state:
            fig_filtered.add_trace(go.Scattergeo(
                lon=[state["lon"]],
                lat=[state["lat"]],
                text=state["abbr"],
                mode='text',
                hoverinfo='skip',
                showlegend=False,
                textfont=dict(size=12, color="darkgrey", family="Arial")
            ))

    fig_filtered.update_layout(
        geo=dict(
            scope="usa",
            projection=dict(type="albers usa"),
            showlakes=True,
            lakecolor="rgb(255, 255, 255)"
        ),
        margin={"r":0,"t":0,"l":0,"b":0},
        height=800,
        width=None
    )

    # Apply pan/zoom if available
    if pan_zoom_data:
        print("Applying pan/zoom data:", pan_zoom_data)
        fig_filtered.update_layout(geo={**fig_filtered.layout.geo.to_plotly_json(), **pan_zoom_data})

    return fig_filtered
 
# Create the map on the initial run
fig = update_map(None, None)
 
app.layout = html.Div(
    style={"height": "100vh", "width": "100vw"},  # Full viewport
    children=[
        html.H1("Plans by County", style={"textAlign": "center", "marginTop": "20px"}),
        dcc.Graph(
            id="county-map",
            figure=fig,
            style={"height": "70vh", "width": "100vw"}
        ),
        dcc.Dropdown(
            id="industry-dropdown",
            options=[
                {"label": industry, "value": code}
                for industry, code in main_industry_pairs
            ],
            value=None,
            multi=True,
            style={"width": "400px", "margin": "20px auto"},
        ),
        dcc.Store(id="pan-zoom-store", storage_type="session")
    ]
)

if __name__ == "__main__":
    app.run_server(debug=True)