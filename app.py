import json
import requests
import streamlit as st


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


st.title("Route POI Demo")
st.write("Enter a start and end coordinate, then query accessibility POIs near the route.")

col1, col2 = st.columns(2)

with col1:
    start_lat = st.number_input("Start latitude", value=42.406172, format="%.6f")
    start_lon = st.number_input("Start longitude", value=-71.120207, format="%.6f")

with col2:
    end_lat = st.number_input("End latitude", value=42.405946, format="%.6f")
    end_lon = st.number_input("End longitude", value=-71.120309, format="%.6f")

distance_m = st.slider("Corridor distance (meters)", min_value=1, max_value=50, value=3)

if st.button("Query POIs"):
    try:
        results = query_pois(start_lon, start_lat, end_lon, end_lat, distance_m)
        st.success(f"Found {len(results)} POIs")
        st.json(results)
    except Exception as e:
        st.error(f"Query failed: {e}")