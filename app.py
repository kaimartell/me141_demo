import json
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium


POI_URL = "https://services3.arcgis.com/iuNbZYJOrAYBrPyC/arcgis/rest/services/survey123_7932a20fc6b14b7d9e48cbdb5e383a9c_results/FeatureServer/0/query"

BASEMAP_SERVICE = "https://services7.arcgis.com/UlEfxLrnpFcC1i8z/ArcGIS/rest/services/Tufts_University_Basemap/FeatureServer"

# Basemap surface layers
GRAVEL_LAYER_ID = 14   # all are gravel paths
SIDEWALK_LAYER_ID = 15 # Type = SWALK or BRIDGE SWALK
PATH_LAYER_ID = 16     # Type = PAVED or UNPAVED

CORRIDOR_DISTANCE_M = 10


def generate_polyline(route_points):
    return {
        "paths": [route_points],
        "spatialReference": {"wkid": 4326}
    }


def arcgis_intersects_params(route_points, out_fields="*"):
    polyline = generate_polyline(route_points)
    return {
        "geometry": json.dumps(polyline),
        "geometryType": "esriGeometryPolyline",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": CORRIDOR_DISTANCE_M,
        "units": "esriSRUnit_Meter",
        "outFields": out_fields,
        "returnGeometry": "true",
        "f": "json"
    }


def query_pois(route_points):
    params = arcgis_intersects_params(
        route_points,
        out_fields="obstacle_category,obstacle_type,severity"
    )

    response = requests.get(POI_URL, params=params, timeout=30)
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


def query_basemap_layer(route_points, layer_id, out_fields="OBJECTID,Type,Name,Campus,Source,Updated"):
    url = f"{BASEMAP_SERVICE}/{layer_id}/query"
    params = arcgis_intersects_params(route_points, out_fields=out_fields)

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("features", [])


def classify_route_surface(route_points):
    """
    Returns a summary of what surface/path types the route intersects.
    Layer logic:
      14 -> gravel path
      15 -> sidewalk types (SWALK / BRIDGE SWALK)
      16 -> path types (PAVED / UNPAVED)
    """
    gravel_features = query_basemap_layer(route_points, GRAVEL_LAYER_ID, out_fields="OBJECTID,Campus,Source,Updated")
    sidewalk_features = query_basemap_layer(route_points, SIDEWALK_LAYER_ID, out_fields="OBJECTID,Type,Campus,Source,Updated")
    path_features = query_basemap_layer(route_points, PATH_LAYER_ID, out_fields="OBJECTID,Type,Name,Campus,Source,Updated")

    surface_types = []
    matched_segments = []

    # Layer 14: gravel paths
    if gravel_features:
        surface_types.append("GRAVEL")
        for feature in gravel_features:
            attr = feature["attributes"]
            matched_segments.append({
                "layer": 14,
                "classification": "GRAVEL",
                "objectid": attr.get("OBJECTID"),
                "type": "GRAVEL",
                "name": None,
                "campus": attr.get("Campus"),
                "source": attr.get("Source"),
                "updated": attr.get("Updated")
            })

    # Layer 15: sidewalks
    sidewalk_type_set = set()
    for feature in sidewalk_features:
        attr = feature["attributes"]
        surface_type = attr.get("Type")
        if surface_type:
            sidewalk_type_set.add(surface_type)
        matched_segments.append({
            "layer": 15,
            "classification": surface_type,
            "objectid": attr.get("OBJECTID"),
            "type": surface_type,
            "name": None,
            "campus": attr.get("Campus"),
            "source": attr.get("Source"),
            "updated": attr.get("Updated")
        })

    # Layer 16: paved/unpaved paths
    path_type_set = set()
    for feature in path_features:
        attr = feature["attributes"]
        surface_type = attr.get("Type")
        if surface_type:
            path_type_set.add(surface_type)
        matched_segments.append({
            "layer": 16,
            "classification": surface_type,
            "objectid": attr.get("OBJECTID"),
            "type": surface_type,
            "name": attr.get("Name"),
            "campus": attr.get("Campus"),
            "source": attr.get("Source"),
            "updated": attr.get("Updated")
        })

    surface_types.extend(sorted(sidewalk_type_set))
    surface_types.extend(sorted(path_type_set))

    # Deduplicate while preserving order
    deduped_surface_types = list(dict.fromkeys(surface_types))

    return {
        "route_surface_types": deduped_surface_types,
        "has_gravel": "GRAVEL" in deduped_surface_types,
        "has_sidewalk": any(t in deduped_surface_types for t in ["SWALK", "BRIDGE SWALK"]),
        "has_path": any(t in deduped_surface_types for t in ["PAVED", "UNPAVED"]),
        "matched_segment_count": len(matched_segments),
        "matched_segments": matched_segments
    }


def query_route(route_points):
    poi_results = query_pois(route_points)
    surface_results = classify_route_surface(route_points)

    return {
        "corridor_distance_m": CORRIDOR_DISTANCE_M,
        "route_point_count": len(route_points),
        "surface_summary": surface_results,
        "pois": poi_results
    }


def route_instruction():
    if not st.session_state.collecting_route and len(st.session_state.route_points) == 0:
        return "Click **Start New Route**, then click points on the map to trace the path."
    if st.session_state.collecting_route:
        if len(st.session_state.route_points) == 0:
            return "Click on the map to place the first route point."
        return "Keep clicking on the map to add more route points. When done, click **Finish Route**."
    if len(st.session_state.route_points) < 2:
        return "Your route needs at least 2 points."

    return "Route finished. Click **Query Route Data** to return obstacles and surface/path types within 10 meters of the route."


# -----------------------
# Session state
# -----------------------

st.set_page_config(page_title="Demo", layout="wide")

if "route_points" not in st.session_state:
    st.session_state.route_points = []

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

left_col, right_col = st.columns([2, 1])

with right_col:
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

    if st.button("Query Route Data", disabled=not query_ready):
        route_points_arcgis = [
            [pt["lon"], pt["lat"]] for pt in st.session_state.route_points
        ]
        try:
            st.session_state.results = query_route(route_points_arcgis)

            poi_count = len(st.session_state.results["pois"])
            surface_types = st.session_state.results["surface_summary"]["route_surface_types"]
            st.success(f"Found {poi_count} POIs. Surface types: {surface_types if surface_types else 'None'}")
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

    if len(st.session_state.route_points) >= 2:
        folium.PolyLine(
            [[pt["lat"], pt["lon"]] for pt in st.session_state.route_points],
            color="blue",
            weight=4
        ).add_to(m)

    if st.session_state.results and st.session_state.results.get("pois"):
        for poi in st.session_state.results["pois"]:
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

        if click_key != st.session_state.last_click_key:
            st.session_state.last_click_key = click_key
            st.session_state.route_points.append({
                "lat": clicked_lat,
                "lon": clicked_lon
            })
            st.session_state.results = None