import json
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium


URL = "https://services3.arcgis.com/iuNbZYJOrAYBrPyC/arcgis/rest/services/survey123_7932a20fc6b14b7d9e48cbdb5e383a9c_results/FeatureServer/0/query"


def generate_polyline(start, end):
    return {
        "paths": [[start, end]],
        "spatialReference": {"wkid": 4326}
    }


def query_pois(start_lon, start_lat, end_lon, end_lat, distance_m):
    start_point = [start_lon, start_lat]
    end_point = [end_lon, end_lat]
    polyline = generate_polyline(start_point, end_point)

    params = {
        "geometry": json.dumps(polyline),
        "geometryType": "esriGeometryPolyline",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": distance_m,
        "units": "esriSRUnit_Meter",
        "outFields": "obstacle_category,obstacle_type,severity",
        "returnGeometry": "true",
        "f": "json"
    }

    response = requests.get(URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    results = []
    for f in data.get("features", []):
        attr = f["attributes"]
        geom = f["geometry"]

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


# -----------------------
# Streamlit app setup
# -----------------------

st.set_page_config(page_title="Route POI Demo", layout="wide")
st.title("Route POI Demo")
st.write("Click on the map to set a start point and an end point, then query nearby accessibility POIs.")

# Default center near Tufts
DEFAULT_CENTER = [42.4065, -71.1205]

if "start_point" not in st.session_state:
    st.session_state.start_point = None

if "end_point" not in st.session_state:
    st.session_state.end_point = None

if "click_mode" not in st.session_state:
    st.session_state.click_mode = "start"

if "results" not in st.session_state:
    st.session_state.results = None


col_left, col_right = st.columns([2, 1])

with col_right:
    st.subheader("Controls")

    distance_m = st.slider("Corridor distance (meters)", min_value=1, max_value=50, value=3)

    st.write(f"Currently selecting: **{st.session_state.click_mode} point**")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Set Start"):
            st.session_state.click_mode = "start"
    with c2:
        if st.button("Set End"):
            st.session_state.click_mode = "end"
    with c3:
        if st.button("Clear"):
            st.session_state.start_point = None
            st.session_state.end_point = None
            st.session_state.results = None
            st.session_state.click_mode = "start"

    st.subheader("Selected Coordinates")

    if st.session_state.start_point:
        st.write(
            f"**Start:** lat={st.session_state.start_point['lat']:.6f}, "
            f"lon={st.session_state.start_point['lon']:.6f}"
        )
    else:
        st.write("**Start:** not set")

    if st.session_state.end_point:
        st.write(
            f"**End:** lat={st.session_state.end_point['lat']:.6f}, "
            f"lon={st.session_state.end_point['lon']:.6f}"
        )
    else:
        st.write("**End:** not set")

    can_query = st.session_state.start_point is not None and st.session_state.end_point is not None

    if st.button("Query POIs", disabled=not can_query):
        try:
            start = st.session_state.start_point
            end = st.session_state.end_point

            st.session_state.results = query_pois(
                start_lon=start["lon"],
                start_lat=start["lat"],
                end_lon=end["lon"],
                end_lat=end["lat"],
                distance_m=distance_m
            )
            st.success(f"Found {len(st.session_state.results)} POIs")
        except Exception as e:
            st.session_state.results = None
            st.error(f"Query failed: {e}")

    if st.session_state.results is not None:
        st.subheader("Results")
        st.json(st.session_state.results)

with col_left:
    st.subheader("Map")

    m = folium.Map(location=DEFAULT_CENTER, zoom_start=17)

    # Existing selected points
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

    # Draw line if both points exist
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

        if st.session_state.click_mode == "start":
            new_point = {"lat": clicked_lat, "lon": clicked_lon}
            if st.session_state.start_point != new_point:
                st.session_state.start_point = new_point
                st.rerun()

        elif st.session_state.click_mode == "end":
            new_point = {"lat": clicked_lat, "lon": clicked_lon}
            if st.session_state.end_point != new_point:
                st.session_state.end_point = new_point
                st.rerun()