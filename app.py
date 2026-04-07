import json
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium


URL = "https://services3.arcgis.com/iuNbZYJOrAYBrPyC/arcgis/rest/services/survey123_7932a20fc6b14b7d9e48cbdb5e383a9c_results/FeatureServer/0/query"
CORRIDOR_DISTANCE_M = 10


def generate_polyline(route_points):
    # route_points must be [[lon, lat], [lon, lat], ...]
    return {
        "paths": [route_points],
        "spatialReference": {"wkid": 4326}
    }


def query_pois(route_points):
    polyline = generate_polyline(route_points)

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


def route_instruction():
    if not st.session_state.collecting_route and len(st.session_state.route_points) == 0:
        return "Click **Start New Route**, then click points on the map to trace the path."
    if st.session_state.collecting_route:
        if len(st.session_state.route_points) == 0:
            return "Click on the map to place the first route point."
        return "Keep clicking on the map to add more route points. When done, click **Finish Route**."
    if len(st.session_state.route_points) < 2:
        return "Your route needs at least 2 points."
    
    
    return "Route finished. Click **Query POIs** to return obstacles within 10 meters of the route."


# -----------------------
# Session state
# -----------------------

st.set_page_config(page_title="Demo", layout="wide")

if "route_points" not in st.session_state:
    st.session_state.route_points = []   # list of {"lat": ..., "lon": ...}

if "collecting_route" not in st.session_state:
    st.session_state.collecting_route = False

if "results" not in st.session_state:
    st.session_state.results = None

if "last_click_key" not in st.session_state:
    st.session_state.last_click_key = None


# -----------------------
# UI
# -----------------------

st.title("Demo")
# st.write("Build a route by clicking multiple points on the map, then query accessibility POIs near that route.")

left_col, right_col = st.columns([2, 1])

with right_col:
    #st.subheader("Instructions")
    #st.info(route_instruction())

    #st.write(f"Corridor distance: **{CORRIDOR_DISTANCE_M} meters**")

    c1, c2 = st.columns(2)

    with c1:
        if st.button("Start New Route"):
            st.session_state.route_points = []
            st.session_state.results = None
            st.session_state.collecting_route = True
            st.session_state.last_click_key = None

    with c2:
        if st.button("Finish Route"):
            st.session_state.collecting_route = False

    c3, c4 = st.columns(2)

    with c3:
        if st.button("Undo Last Point"):
            if st.session_state.route_points:
                st.session_state.route_points = st.session_state.route_points[:-1]
                st.session_state.results = None

    with c4:
        if st.button("Clear Route"):
            st.session_state.route_points = []
            st.session_state.results = None
            st.session_state.collecting_route = False
            st.session_state.last_click_key = None

    st.subheader("Route Points")
    if st.session_state.route_points:
        for i, pt in enumerate(st.session_state.route_points, start=1):
            st.write(f"{i}. lat={pt['lat']:.6f}, lon={pt['lon']:.6f}")
    else:
        st.write("No route points selected yet.")

    query_ready = len(st.session_state.route_points) >= 2 and not st.session_state.collecting_route

    if st.button("Query POIs", disabled=not query_ready):
        route_points_arcgis = [
            [pt["lon"], pt["lat"]] for pt in st.session_state.route_points
        ]
        try:
            st.session_state.results = query_pois(route_points_arcgis)
            st.success(f"Found {len(st.session_state.results)} POIs")
        except Exception as e:
            st.session_state.results = None
            st.error(f"Query failed: {e}")

    if st.session_state.results is not None:
        st.subheader("Results")
        st.json(st.session_state.results)

with left_col:
    st.subheader("Map")

    DEFAULT_CENTER = [42.4065, -71.1205]
    m = folium.Map(location=DEFAULT_CENTER, zoom_start=17)

    # Draw clicked route vertices
    for i, pt in enumerate(st.session_state.route_points):
        label = f"Point {i+1}"
        folium.CircleMarker(
            [pt["lat"], pt["lon"]],
            radius=5,
            popup=label,
            tooltip=label,
            color="blue",
            fill=True
        ).add_to(m)

    # Draw route if 2+ points
    if len(st.session_state.route_points) >= 2:
        folium.PolyLine(
            [[pt["lat"], pt["lon"]] for pt in st.session_state.route_points],
            color="blue",
            weight=4
        ).add_to(m)

    # Draw returned POIs
    if st.session_state.results:
        for poi in st.session_state.results:
            lat = poi["location"]["lat"]
            lon = poi["location"]["lon"]
            popup_text = (
                f"{poi['category']}<br>"
                f"{poi['type']}<br>"
                f"Severity: {poi['severity']}"
            )
            folium.Marker(
                [lat, lon],
                popup=popup_text,
                icon=folium.Icon(color="red")
            ).add_to(m)

    map_data = st_folium(m, width=900, height=600, key="route_map")
    clicked = map_data.get("last_clicked")

    if clicked and st.session_state.collecting_route:
        clicked_lat = clicked["lat"]
        clicked_lon = clicked["lng"]
        click_key = f"{clicked_lat:.6f},{clicked_lon:.6f}"

        # Prevent duplicate add from same click across reruns
        if click_key != st.session_state.last_click_key:
            st.session_state.last_click_key = click_key
            st.session_state.route_points.append({
                "lat": clicked_lat,
                "lon": clicked_lon
            })
            st.session_state.results = None