"""Data Crokinole Page - Modernized static site integration."""

import streamlit as st
from pathlib import Path


def render():
    """Render the Data Crokinole page with embedded modernized site."""
    st.title("🎯 DataCrokinole FTT")
    
    st.info("""
    **FlickSkill Through Time (FTT) Rankings & Statistics**
    
    A DataGolf-inspired statistics portal featuring FlickSkill rankings, season points, 
    and tournament data. The site uses client-side rendering for fast, interactive browsing.
    """)
    
    # Check if files exist
    html_file = Path("static_site_v2/index.html")
    css_file = Path("static_site_v2/dc_styles.css")
    js_file = Path("static_site_v2/dc_app.js")
    data_file = Path("static_site_v2/player_data.json")
    
    st.write("**File Status:**")
    st.write(f"- HTML: {'✅ Found' if html_file.exists() else '❌ Missing'}")
    st.write(f"- CSS: {'✅ Found' if css_file.exists() else '❌ Missing'}")
    st.write(f"- JS: {'✅ Found' if js_file.exists() else '❌ Missing'}")
    st.write(f"- Data: {'✅ Found' if data_file.exists() else '❌ Missing'}")
    
    if not all([html_file.exists(), css_file.exists(), js_file.exists(), data_file.exists()]):
        st.error("❌ Some files are missing. Please run `python3 generate_dc_data.py` first.")
        return
    
    try:
        # Read all files
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        with open(css_file, 'r', encoding='utf-8') as f:
            css_content = f.read()
        
        with open(js_file, 'r', encoding='utf-8') as f:
            js_content = f.read()
        
        with open(data_file, 'r', encoding='utf-8') as f:
            player_data = f.read()
        
        st.success("✅ All files loaded successfully!")
        
        # Extract body content
        body_start = html_content.find('<body>')
        body_end = html_content.find('</body>')
        if body_start == -1 or body_end == -1:
            st.error("❌ Could not find body tags in HTML")
            return
        
        body_content = html_content[body_start + 6:body_end]
        
        # Combine everything
        combined_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Data Crokinole</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
    <style>
    {css_content}
    </style>
</head>
<body>
{body_content.replace('<script src="dc_app.js"></script>', '')}

<script>
// Embed player data directly
window.PLAYER_DATA = {player_data};

// Embed the full application code
{js_content}
</script>
</body>
</html>
"""
        
        # Embed in Streamlit
        st.components.v1.html(combined_html, height=900, scrolling=True)
        
    except Exception as e:
        st.error(f"❌ Error loading site: {e}")
        import traceback
        st.code(traceback.format_exc())

