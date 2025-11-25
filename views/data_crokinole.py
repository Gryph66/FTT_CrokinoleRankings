"""Data Crokinole Page - Modernized static site integration."""

import streamlit as st
from pathlib import Path


def render():
    """Render the Data Crokinole page with embedded modernized site."""
    st.title("📊 Data Crokinole - Modernized")
    
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
    <style>
    {css_content}
    </style>
</head>
<body>
{body_content}

<script>
// Embed player data directly
const PLAYER_DATA = {player_data};

// Modified app to use embedded data
class DataCrokinoleApp {{
    constructor() {{
        this.playerData = PLAYER_DATA;
        this.currentPage = 'rankings';
        this.currentFilter = 'all';
        this.searchTerm = '';
        this.rankingsPage = 1;
        this.rankingsPerPage = 50;
        
        this.init();
    }}
    
    async init() {{
        // Setup event listeners
        this.setupNavigation();
        this.setupFilters();
        this.setupSearch();
        this.setupPagination();
        
        // Initial render
        this.renderRankings();
        this.updateStats();
        this.updateTimestamp();
    }}
    
    updateTimestamp() {{
        const now = new Date();
        document.getElementById('lastUpdated').textContent = 
            `Updated ${{now.toLocaleDateString('en-US', {{ month: 'long', day: 'numeric', year: 'numeric' }})}} at ${{now.toLocaleTimeString('en-US', {{ hour: '2-digit', minute: '2-digit' }})}}`;
    }}
    
    {js_content.split('async loadData()')[1].split('async init()')[0] if 'async loadData()' in js_content else ''}
    
    setupNavigation() {{
        document.querySelectorAll('.nav-link').forEach(link => {{
            link.addEventListener('click', (e) => {{
                e.preventDefault();
                const page = e.target.dataset.page;
                this.navigateTo(page);
            }});
        }});
    }}
    
    navigateTo(page) {{
        document.querySelectorAll('.nav-link').forEach(link => {{
            link.classList.toggle('active', link.dataset.page === page);
        }});
        
        document.querySelectorAll('.page-section').forEach(section => {{
            section.classList.toggle('active', section.id === `${{page}}-page`);
        }});
        
        this.currentPage = page;
        
        if (page === 'rankings') {{
            this.renderRankings();
        }} else if (page === 'points') {{
            this.renderPoints();
        }} else if (page === 'tournaments') {{
            this.renderTournaments();
        }}
    }}
    
    setupFilters() {{
        document.querySelectorAll('.filter-btn').forEach(btn => {{
            btn.addEventListener('click', (e) => {{
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.currentFilter = e.target.dataset.filter;
                this.rankingsPage = 1;
                this.renderRankings();
            }});
        }});
    }}
    
    setupSearch() {{
        const searchBox = document.getElementById('searchBox');
        searchBox.addEventListener('input', (e) => {{
            this.searchTerm = e.target.value.toLowerCase();
            this.rankingsPage = 1;
            this.renderRankings();
        }});
    }}
    
    setupPagination() {{
        document.getElementById('prevPage').addEventListener('click', () => {{
            if (this.rankingsPage > 1) {{
                this.rankingsPage--;
                this.renderRankings();
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
        }});
        
        document.getElementById('nextPage').addEventListener('click', () => {{
            const filtered = this.getFilteredPlayers();
            const maxPage = Math.ceil(filtered.length / this.rankingsPerPage);
            if (this.rankingsPage < maxPage) {{
                this.rankingsPage++;
                this.renderRankings();
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
        }});
    }}
    
    getFilteredPlayers() {{
        if (!this.playerData || !this.playerData.players) return [];
        
        return this.playerData.players.filter(player => {{
            if (this.currentFilter !== 'all' && !player.tours.includes(this.currentFilter)) {{
                return false;
            }}
            
            if (this.searchTerm && !player.name.toLowerCase().includes(this.searchTerm)) {{
                return false;
            }}
            
            return true;
        }});
    }}
    
    renderRankings() {{
        const tbody = document.getElementById('rankingsTableBody');
        const filtered = this.getFilteredPlayers();
        
        if (filtered.length === 0) {{
            tbody.innerHTML = '<tr><td colspan="8" style="padding: 40px; text-align: center; color: #666;">No players found</td></tr>';
            return;
        }}
        
        const start = (this.rankingsPage - 1) * this.rankingsPerPage;
        const end = start + this.rankingsPerPage;
        const paginated = filtered.slice(start, end);
        
        tbody.innerHTML = paginated.map((player, idx) => {{
            const rank = start + idx + 1;
            const isTop3 = rank <= 3;
            
            return `
                <tr class="${{isTop3 ? 'top-3' : ''}}" data-player="${{player.name.toLowerCase()}}" data-tours="${{player.tours}}">
                    <td class="rank-cell">${{rank}}</td>
                    <td class="player-cell">
                        <a href="player_profile.html?id=${{player.id}}" class="player-link">${{player.name}}</a>
                    </td>
                    <td class="tours-cell">${{this.renderTourBadges(player.tours)}}</td>
                    <td class="trend-cell">${{this.renderSparkline(player.history)}}</td>
                    <td>${{player.rating.toFixed(2)}}</td>
                    <td>${{player.mu.toFixed(2)}}</td>
                    <td>${{player.sigma.toFixed(2)}}</td>
                    <td>${{player.tournaments}}</td>
                </tr>
            `;
        }}).join('');
        
        this.updatePagination(filtered.length);
    }}
    
    renderTourBadges(tours) {{
        if (!tours) return '';
        const tourList = tours.split(',');
        return tourList.map(tour => {{
            const color = tour === 'NCA' ? '#ff6b6b' : tour === 'UK' ? '#4a90e2' : '#95a5a6';
            return `<span class="tour-badge" style="background-color: ${{color}};">${{tour}}</span>`;
        }}).join('');
    }}
    
    renderSparkline(history) {{
        if (!history || history.length < 2) {{
            return '<svg width="100" height="20"></svg>';
        }}
        
        const values = history.slice(-10);
        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min || 1;
        
        const points = values.map((val, idx) => {{
            const x = (idx / (values.length - 1)) * 100;
            const y = 20 - ((val - min) / range) * 20;
            return `${{x.toFixed(1)}},${{y.toFixed(1)}}`;
        }}).join(' ');
        
        return `<svg width="100" height="20" class="sparkline">
            <polyline points="${{points}}" fill="none" stroke="#999999" stroke-width="1.2" />
        </svg>`;
    }}
    
    updatePagination(totalFiltered) {{
        const maxPage = Math.ceil(totalFiltered / this.rankingsPerPage);
        const start = (this.rankingsPage - 1) * this.rankingsPerPage + 1;
        const end = Math.min(this.rankingsPage * this.rankingsPerPage, totalFiltered);
        
        document.getElementById('pageInfo').textContent = 
            `Showing ${{start}}-${{end}} of ${{totalFiltered}} players`;
        
        document.getElementById('prevPage').disabled = this.rankingsPage === 1;
        document.getElementById('nextPage').disabled = this.rankingsPage >= maxPage;
    }}
    
    updateStats() {{
        if (!this.playerData || !this.playerData.players) return;
        
        document.getElementById('totalPlayers').textContent = this.playerData.players.length;
        document.getElementById('totalTournaments').textContent = this.playerData.total_tournaments || '-';
        
        const avgRating = this.playerData.players.reduce((sum, p) => sum + p.rating, 0) / this.playerData.players.length;
        document.getElementById('avgRating').textContent = avgRating.toFixed(1);
    }}
    
    renderPoints() {{
        const tbody = document.getElementById('pointsTableBody');
        
        if (!this.playerData || !this.playerData.season_points) {{
            tbody.innerHTML = '<tr><td colspan="6" style="padding: 40px; text-align: center; color: #666;">No points data available</td></tr>';
            return;
        }}
        
        tbody.innerHTML = this.playerData.season_points.map((entry, idx) => `
            <tr>
                <td class="rank-cell">${{idx + 1}}</td>
                <td class="player-cell">
                    <a href="player_profile.html?id=${{entry.player_id}}" class="player-link">${{entry.player_name}}</a>
                </td>
                <td>${{entry.season}}</td>
                <td>${{entry.total_points.toFixed(2)}}</td>
                <td>${{entry.events}}</td>
                <td>${{(entry.total_points / entry.events).toFixed(2)}}</td>
            </tr>
        `).join('');
    }}
    
    renderTournaments() {{
        const tbody = document.getElementById('tournamentsTableBody');
        
        if (!this.playerData || !this.playerData.tournaments) {{
            tbody.innerHTML = '<tr><td colspan="6" style="padding: 40px; text-align: center; color: #666;">No tournament data available</td></tr>';
            return;
        }}
        
        tbody.innerHTML = this.playerData.tournaments.map(tournament => `
            <tr>
                <td style="text-align: left;">
                    <a href="tournaments/${{tournament.id}}.html" class="player-link">${{tournament.name}}</a>
                </td>
                <td>${{tournament.date}}</td>
                <td>${{tournament.season}}</td>
                <td>${{tournament.format}}</td>
                <td>${{tournament.fsi ? tournament.fsi.toFixed(2) : '-'}}</td>
                <td>${{tournament.players}}</td>
            </tr>
        `).join('');
    }}
}}

document.addEventListener('DOMContentLoaded', () => {{
    window.dcApp = new DataCrokinoleApp();
}});
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

