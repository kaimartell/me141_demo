import json
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium


POI_URL = "https://services3.arcgis.com/iuNbZYJOrAYBrPyC/arcgis/rest/services/survey123_7932a20fc6b14b7d9e48cbdb5e383a9c_results/FeatureServer/0/query"

BASEMAP_SERVICE = "https://services7.arcgis.com/UlEfxLrnpFcC1i8z/ArcGIS/rest/services/Tufts_University_Basemap/FeatureServer"

GRAVEL_LAYER_ID = 14
SIDEWALK_LAYER_ID = 15
PATH_LAYER_ID = 16

CORRIDOR_DISTANCE_M = 10


def generate_polyline(route_points):
    return {
        "paths": [route_points],
        "spatialReference": {"wkid": 4326}
    }


def arcgis_intersects_params(route_points, out_fields="*", return_geometry=True):
    polyline = generate_polyline(route_points)
    return {
        "geometry": json.dumps(polyline),
        "geometryType": "esriGeometryPolyline",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": CORRIDOR_DISTANCE_M,
        "units": "esriSRUnit_Meter",
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
        "f": "json"
    }


def query_pois(route_points):
    params = arcgis_intersects_params(
        route_points,
        out_fields="obstacle_category,obstacle_type,severity",
        return_geometry=True
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


def ring_to_latlon(ring):
    # ArcGIS polygon rings are [x, y] = [lon, lat]
    return [[pt[1], pt[0]] for pt in ring]


def feature_geometry_to_latlon_polygons(feature):
    geom = feature.get("geometry", {})
    rings = geom.get("rings", [])
    if not rings:
        return []

    polygons = []
    for ring in rings:
        if ring:
            polygons.append(ring_to_latlon(ring))
    return polygons


def query_basemap_layer(route_points, layer_id, out_fields):
    url = f"{BASEMAP_SERVICE}/{layer_id}/query"
    params = arcgis_intersects_params(
        route_points,
        out_fields=out_fields,
        return_geometry=True
    )

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("features", [])


def classify_route_surface(route_points):
    gravel_features = query_basemap_layer(
        route_points,
        GRAVEL_LAYER_ID,
        out_fields="OBJECTID,Campus,Source,Updated"
    )
    sidewalk_features = query_basemap_layer(
        route_points,
        SIDEWALK_LAYER_ID,
        out_fields="OBJECTID,Type,Campus,Source,Updated"
    )
    path_features = query_basemap_layer(
        route_points,
        PATH_LAYER_ID,
        out_fields="OBJECTID,Type,Name,Campus,Source,Updated"
    )

    surface_types = []
    matched_segments = []
    polygon_overlays = []

    # Layer 14: gravel
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

            for polygon in feature_geometry_to_latlon_polygons(feature):
                polygon_overlays.append({
                    "layer": 14,
                    "classification": "GRAVEL",
                    "objectid": attr.get("OBJECTID"),
                    "polygon": polygon
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

        for polygon in feature_geometry_to_latlon_polygons(feature):
            polygon_overlays.append({
                "layer": 15,
                "classification": surface_type,
                "objectid": attr.get("OBJECTID"),
                "polygon": polygon
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

        for polygon in feature_geometry_to_latlon_polygons(feature):
            polygon_overlays.append({
                "layer": 16,
                "classification": surface_type,
                "objectid": attr.get("OBJECTID"),
                "polygon": polygon
            })

    surface_types.extend(sorted(sidewalk_type_set))
    surface_types.extend(sorted(path_type_set))
    deduped_surface_types = list(dict.fromkeys(surface_types))

    return {
        "route_surface_types": deduped_surface_types,
        "has_gravel": "GRAVEL" in deduped_surface_types,
        "has_sidewalk": any(t in deduped_surface_types for t in ["SWALK", "BRIDGE SWALK"]),
        "has_path": any(t in deduped_surface_types for t in ["PAVED", "UNPAVED"]),
        "matched_segment_count": len(matched_segments),
        "matched_segments": matched_segments,
        "polygon_overlays": polygon_overlays
    }


def query_route(route_points):
    poi_results = query_pois(route_points)
    surface_results = classify_route_surface(route_points)

    return {
        "corridor_distance_m": CORRIDOR_DISTANCE_M,
        "route_point_count": len(route_points),
        "pois": poi_results,
        "surface_summary": surface_results
    }


def surface_color(classification):
    if classification == "GRAVEL":
        return "#8c6d46"
    if classification == "PAVED":
        return "#2b8cbe"
    if classification == "UNPAVED":
        return "#31a354"
    if classification == "BRIDGE SWALK":
        return "#756bb1"
    if classification == "SWALK":
        return "#636363"
    return "#ff7f0e"


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
            st.success(
                f"Found {poi_count} POIs. "
                f"Surface/path types: {surface_types if surface_types else 'None'}"
            )
        except Exception as e:
            st.session_state.results = None
            st.error(f"Query failed: {e}")

    if st.session_state.results is not None:
        pois = st.session_state.results.get("pois", [])
        surface_summary = st.session_state.results.get("surface_summary", {})
        matched_segments = surface_summary.get("matched_segments", [])

        with st.expander("POI Results", expanded=True):
            st.json(pois)

        with st.expander("Path / Surface Results", expanded=True):
            st.json({
                "route_surface_types": surface_summary.get("route_surface_types", []),
                "matched_segment_count": surface_summary.get("matched_segment_count", 0),
                "matched_segments": matched_segments
            })

with left_col:
    st.subheader("Map")

    DEFAULT_CENTER = [42.4065, -71.1205]
    m = folium.Map(location=DEFAULT_CENTER, zoom_start=17)

    # Route vertices
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

    # Route line
    if len(st.session_state.route_points) >= 2:
        folium.PolyLine(
            [[pt["lat"], pt["lon"]] for pt in st.session_state.route_points],
            color="blue",
            weight=4
        ).add_to(m)

    # Highlight matched polygons
    if st.session_state.results:
        surface_summary = st.session_state.results.get("surface_summary", {})
        polygon_overlays = surface_summary.get("polygon_overlays", [])

        for overlay in polygon_overlays:
            classification = overlay["classification"]
            color = surface_color(classification)
            popup_text = (
                f"Layer: {overlay['layer']}<br>"
                f"Class: {classification}<br>"
                f"ObjectID: {overlay['objectid']}"
            )

            folium.Polygon(
                locations=overlay["polygon"],
                color=color,
                weight=2,
                fill=True,
                fill_opacity=0.35,
                popup=popup_text,
                tooltip=classification
            ).add_to(m)

    # POI markers
    if st.session_state.results:
        for poi in st.session_state.results.get("pois", []):
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