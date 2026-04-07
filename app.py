import json
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium


URL = "https://services3.arcgis.com/iuNbZYJOrAYBrPyC/arcgis/rest/services/survey123_7932a20fc6b14b7d9e48cbdb5e383a9c_results/FeatureServer/0/query"
CORRIDOR_DISTANCE_M = 5


def generate_polyline(start, end):
    return {
        "paths": [[start, end]],
        "spatialReference": {"wkid": 4326}
    }


def query_pois(start_lon, start_lat, end_lon, end_lat):
    start_point = [start_lon, start_lat]  # ArcGIS order: [x, y] = [lon, lat]
    end_point = [end_lon, end_lat]
    polyline = generate_polyline(start_point, end_point)

    params = {
        "geometry": json.dumps(polyline),
        "geometryType": "esriGeometryPolyline",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": CORRIDOR_DISTANCE_M,
        "units": "esriSRUnit_Meter",
        "outFields": "obstacle_category,obstacle_type,severity",
        "returnGeometry": "true",
        "f": "json"
    }

    response = requests.get(URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    results = []
    for feature in data.get("features", []):
        attr = feature["attributes"]
        geom = feature["geometry"]

        results.append({
            "category": attr.get("obstacle_category"),
            "type": attr.get("obstacle_type"),
            "severity": attr.get("severity"),
            "location": {
                "lat": geom.get("y"),
                "lon": geom.get("x")
            }
        })

    return results


def get_instruction_text():
    if st.session_state.start_point is None:
        return "Step 1: Click on the map to choose the start point."
    elif st.session_state.end_point is None:
        return "Step 2: Click on the map to choose the end point."
    return "Step 3: Click 'Query POIs' to return obstacles along the route."


# -----------------------
# Streamlit app setup
# -----------------------

st.set_page_config(page_title="Route POI Demo", layout="wide")
st.title("Route POI Demo")
st.write("Pick a start point, then an end point, then query accessibility POIs within 5 meters of the route.")

DEFAULT_CENTER = [42.4065, -71.1205]

if "start_point" not in st.session_state:
    st.session_state.start_point = None

if "end_point" not in st.session_state:
    st.session_state.end_point = None

if "results" not in st.session_state:
    st.session_state.results = None

if "last_click_key" not in st.session_state:
    st.session_state.last_click_key = None


left_col, right_col = st.columns([2, 1])

with right_col:
    st.subheader("Instructions")
    st.info(get_instruction_text())

    st.write(f"Corridor distance: **{CORRIDOR_DISTANCE_M} meters**")

    st.subheader("Selected Points")

    if st.session_state.start_point:
        st.write(
            f"**Start**  \nlat: `{st.session_state.start_point['lat']:.6f}`  \nlon: `{st.session_state.start_point['lon']:.6f}`"
        )
    else:
        st.write("**Start:** not selected")

    if st.session_state.end_point:
        st.write(
            f"**End**  \nlat: `{st.session_state.end_point['lat']:.6f}`  \nlon: `{st.session_state.end_point['lon']:.6f}`"
        )
    else:
        st.write("**End:** not selected")

    query_ready = (
        st.session_state.start_point is not None
        and st.session_state.end_point is not None
    )

    if st.button("Query POIs", disabled=not query_ready):
        try:
            start = st.session_state.start_point
            end = st.session_state.end_point

            st.session_state.results = query_pois(
                start_lon=start["lon"],
                start_lat=start["lat"],
                end_lon=end["lon"],
                end_lat=end["lat"]
            )

            st.success(f"Found {len(st.session_state.results)} POIs")

        except Exception as e:
            st.session_state.results = None
            st.error(f"Query failed: {e}")

    if st.button("Reset"):
        st.session_state.start_point = None
        st.session_state.end_point = None
        st.session_state.results = None
        st.session_state.last_click_key = None
        st.rerun()

    if st.session_state.results is not None:
        st.subheader("Results")
        st.json(st.session_state.results)

with left_col:
    st.subheader("Map")

    m = folium.Map(location=DEFAULT_CENTER, zoom_start=17)

    if st.session_state.start_point:
        folium.Marker(
            [st.session_state.start_point["lat"], st.session_state.start_point["lon"]],
            popup="Start",
            tooltip="Start",
            icon=folium.Icon(color="green")
        ).add_to(m)

    if st.session_state.end_point:
        folium.Marker(
            [st.session_state.end_point["lat"], st.session_state.end_point["lon"]],
            popup="End",
            tooltip="End",
            icon=folium.Icon(color="red")
        ).add_to(m)

    if st.session_state.start_point and st.session_state.end_point:
        folium.PolyLine(
            [
                [st.session_state.start_point["lat"], st.session_state.start_point["lon"]],
                [st.session_state.end_point["lat"], st.session_state.end_point["lon"]],
            ],
            color="blue",
            weight=4
        ).add_to(m)

    map_data = st_folium(m, width=900, height=600)
    clicked = map_data.get("last_clicked")

    if clicked:
        clicked_lat = clicked["lat"]
        clicked_lon = clicked["lng"]
        click_key = f"{clicked_lat:.6f},{clicked_lon:.6f}"

        if click_key != st.session_state.last_click_key:
            st.session_state.last_click_key = click_key

            new_point = {"lat": clicked_lat, "lon": clicked_lon}

            if st.session_state.start_point is None:
                st.session_state.start_point = new_point
                st.session_state.results = None
                st.rerun()

            elif st.session_state.end_point is None:
                st.session_state.end_point = new_point
                st.session_state.results = None
                st.rerun()