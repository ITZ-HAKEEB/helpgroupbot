import os
import logging
import tempfile
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Primary Assets Path
ASSETS_BG = "/Users/nishkarshkumar/Desktop/Doraemon/titanic-saver/assets/background.jpg"
if not os.path.exists(ASSETS_BG):
    ASSETS_BG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "background.jpg")

def generate_leaderboard_image(group_title: str, users: list, timeframe: str = "daily") -> str:
    """
    Generate dynamic HTML/CSS leaderboard image with starry night background & group title.
    Returns path to output PNG image file.
    """
    timeframe_labels = {
        "daily": "Daily Today",
        "weekly": "Weekly This Week",
        "overall": "Overall All-Time"
    }
    timeframe_title = timeframe_labels.get(timeframe, "Overall All-Time")

    # Format users list up to 10 entries with default colors/avatars
    formatted_users = []
    colors = ["#ffd700", "#1e90ff", "#ff69b4", "#ff4500", "#32cd32", "#9370db", "#ff1493", "#00ced1", "#dc143c", "#4169e1"]

    for i in range(10):
        if i < len(users):
            u = users[i]
            uname = u.get("name", f"User {i+1}")
            ucount = u.get("count", 0)
        else:
            uname = "No User"
            ucount = 0

        initial = uname[0].upper() if uname else "?"
        formatted_users.append({
            "name": uname,
            "count": ucount,
            "avatar": initial,
            "color": colors[i % len(colors)]
        })

    top3 = formatted_users[:3]
    ranks_4_10 = formatted_users[3:10]

    bg_url = f"file://{os.path.abspath(ASSETS_BG)}" if os.path.exists(ASSETS_BG) else ""

    html_template = f"""
<!DOCTYPE html>
<html>
<head>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@600;800;900&display=swap');
    
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Outfit', sans-serif; }}
    
    body {{
        width: 1536px;
        height: 1024px;
        background-image: url('{bg_url}');
        background-size: cover;
        background-position: center;
        background-color: #05102e;
        color: white;
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 20px;
        position: relative;
        overflow: hidden;
    }}
    
    .bg-overlay {{
        position: absolute;
        top: 0; left: 0; width: 100%; height: 100%;
        background: radial-gradient(circle at 50% 30%, rgba(5, 20, 60, 0.35) 0%, rgba(3, 10, 35, 0.82) 100%);
        z-index: 1;
    }}

    .content {{
        position: relative;
        z-index: 10;
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
    }}
    
    .header {{
        text-align: center;
        margin-top: 5px;
    }}
    
    .title {{
        font-size: 80px;
        font-weight: 900;
        background: linear-gradient(180deg, #fff5a6 0%, #ffd700 40%, #ffa500 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: 4px;
        filter: drop-shadow(0 4px 18px rgba(255, 215, 0, 0.6));
    }}
    
    .subtitle {{
        font-size: 34px;
        font-weight: 800;
        color: #ffffff;
        margin-top: 2px;
        text-shadow: 0 3px 15px rgba(0,0,0,0.9);
    }}

    .body-grid {{
        display: flex;
        width: 100%;
        max-width: 1500px;
        margin-top: 15px;
        justify-content: space-between;
        align-items: flex-start;
    }}

    .side-card {{
        width: 250px;
        background: rgba(8, 28, 75, 0.75);
        border: 2px solid rgba(110, 190, 255, 0.45);
        border-radius: 24px;
        padding: 26px 20px;
        backdrop-filter: blur(14px);
        text-align: center;
        box-shadow: 0 12px 35px rgba(0,0,0,0.5);
    }}
    
    .side-title {{
        font-size: 21px;
        font-weight: 900;
        color: #85c2ff;
        margin-bottom: 14px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    .side-text {{
        font-size: 18px;
        color: #d8e6ff;
        line-height: 1.5;
        font-weight: 600;
    }}

    .side-item {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 12px;
        font-size: 17px;
        font-weight: 800;
        background: rgba(255,255,255,0.12);
        padding: 11px 15px;
        border-radius: 14px;
    }}

    .center-section {{
        flex: 1;
        margin: 0 15px;
        display: flex;
        flex-direction: column;
        align-items: center;
    }}

    .top3-container {{
        display: flex;
        justify-content: center;
        align-items: flex-end;
        gap: 25px;
        width: 100%;
    }}

    .podium-card {{
        background: rgba(10, 36, 95, 0.88);
        border-radius: 28px;
        padding: 24px 20px;
        width: 310px;
        text-align: center;
        border: 4px solid #3b82f6;
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.6);
        position: relative;
        backdrop-filter: blur(14px);
    }}

    .podium-card.rank-1 {{
        border-color: #ffd700;
        background: linear-gradient(180deg, rgba(20, 70, 165, 0.95) 0%, rgba(8, 30, 90, 0.95) 100%);
        box-shadow: 0 0 50px rgba(255, 215, 0, 0.55);
        transform: translateY(-18px);
        width: 345px;
    }}

    .podium-card.rank-2 {{ border-color: #d0d0d0; }}
    .podium-card.rank-3 {{ border-color: #d98236; }}

    .badge {{
        position: absolute;
        top: -24px;
        left: 50%;
        transform: translateX(-50%);
        width: 50px;
        height: 50px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 900;
        font-size: 28px;
        box-shadow: 0 5px 18px rgba(0,0,0,0.5);
    }}
    .rank-1 .badge {{ background: linear-gradient(135deg, #fff485, #ffd700); color: #4a3800; }}
    .rank-2 .badge {{ background: linear-gradient(135deg, #ffffff, #c0c0c0); color: #1a1a1a; }}
    .rank-3 .badge {{ background: linear-gradient(135deg, #f5a666, #cd7f32); color: #ffffff; }}

    .avatar-circle {{
        width: 95px;
        height: 95px;
        border-radius: 50%;
        margin: 12px auto 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 42px;
        font-weight: 900;
        color: white;
        box-shadow: 0 6px 18px rgba(0,0,0,0.4);
        border: 4px solid rgba(255,255,255,0.85);
    }}

    .rank-1 .avatar-circle {{ width: 110px; height: 110px; font-size: 50px; border-color: #ffd700; }}

    .user-name {{
        font-size: 28px;
        font-weight: 900;
        margin-top: 14px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        color: #ffffff;
    }}

    .rank-1 .user-name {{ font-size: 31px; }}

    .user-count {{
        font-size: 26px;
        font-weight: 900;
        color: #ffdf00;
        margin-top: 8px;
    }}

    .rank-1 .user-count {{ font-size: 28px; }}

    .lower-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 14px 25px;
        width: 100%;
        margin-top: 22px;
    }}

    .row-card {{
        background: rgba(8, 30, 85, 0.84);
        border: 2px solid rgba(90, 170, 255, 0.45);
        border-radius: 20px;
        padding: 13px 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        backdrop-filter: blur(10px);
        box-shadow: 0 5px 18px rgba(0,0,0,0.35);
    }}

    .row-left {{
        display: flex;
        align-items: center;
        gap: 18px;
    }}

    .row-rank {{
        font-size: 28px;
        font-weight: 900;
        width: 35px;
        color: #a3ccff;
    }}

    .row-avatar {{
        width: 52px;
        height: 52px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 900;
        font-size: 24px;
        color: white;
        box-shadow: 0 4px 12px rgba(0,0,0,0.35);
    }}

    .row-name {{
        font-size: 24px;
        font-weight: 800;
    }}

    .row-count {{
        font-size: 24px;
        font-weight: 900;
        color: #ffdf00;
    }}

    .footer {{
        margin-top: auto;
        font-size: 26px;
        font-weight: 900;
        color: #ffd700;
        letter-spacing: 2px;
        text-shadow: 0 3px 15px rgba(255, 215, 0, 0.6);
    }}
</style>
</head>
<body>
    <div class="bg-overlay"></div>

    <div class="content">
        <div class="header">
            <div class="title">LEADERBOARD</div>
            <div class="subtitle">👑 Top Chatters of {group_title} ({timeframe_title}) 👑</div>
        </div>

        <div class="body-grid">
            <div class="side-card">
                <div class="side-title">ABOUT LEADERBOARD</div>
                <div class="side-text">
                    Keep chatting, stay active, and climb to the top of the group leaderboard! 🚀✨
                </div>
                <div style="font-size: 55px; margin-top: 25px;">🏆</div>
            </div>

            <div class="center-section">
                <div class="top3-container">
                    <div class="podium-card rank-2">
                        <div class="badge">2</div>
                        <div class="avatar-circle" style="background: {top3[1]['color']};">{top3[1]['avatar']}</div>
                        <div class="user-name">{top3[1]['name']}</div>
                        <div class="user-count">💬 {top3[1]['count']:,}</div>
                    </div>

                    <div class="podium-card rank-1">
                        <div class="badge">1</div>
                        <div class="avatar-circle" style="background: {top3[0]['color']};">{top3[0]['avatar']}</div>
                        <div class="user-name">{top3[0]['name']}</div>
                        <div class="user-count">💬 {top3[0]['count']:,}</div>
                    </div>

                    <div class="podium-card rank-3">
                        <div class="badge">3</div>
                        <div class="avatar-circle" style="background: {top3[2]['color']};">{top3[2]['avatar']}</div>
                        <div class="user-name">{top3[2]['name']}</div>
                        <div class="user-count">💬 {top3[2]['count']:,}</div>
                    </div>
                </div>

                <div class="lower-grid">
"""

    for idx, u in enumerate(ranks_4_10, start=4):
        html_template += f"""
                    <div class="row-card">
                        <div class="row-left">
                            <div class="row-rank">{idx}</div>
                            <div class="row-avatar" style="background: {u['color']};">{u['avatar']}</div>
                            <div class="row-name">{u['name']}</div>
                        </div>
                        <div class="row-count">💬 {u['count']:,}</div>
                    </div>
"""

    html_template += """
                </div>
            </div>

            <div class="side-card">
                <div class="side-title">POINTS INFO</div>
                <div class="side-item"><span>💬 Text Message</span><span>+1</span></div>
                <div class="side-item"><span>🖼 Media / Photo</span><span>+2</span></div>
                <div class="side-item"><span>🎙 Voice Note</span><span>+3</span></div>
                <div class="side-item"><span>🔥 Active Streak</span><span>Bonus</span></div>
            </div>
        </div>

        <div class="footer">⭐ Chat More • Earn More • Be Top Chatter! ⭐</div>
    </div>
</body>
</html>
"""

    output_path = tempfile.mktemp(suffix=".png")
    try:
        from html2image import Html2Image
        hti = Html2Image(output_path=os.path.dirname(output_path), custom_flags=['--no-sandbox', '--disable-gpu'])
        hti.screenshot(html_str=html_template, save_as=os.path.basename(output_path), size=(1536, 1024))
        return output_path
    except Exception as e:
        logger.error(f"html2image screenshot error: {e}")
        # Fallback to PIL drawer if headless browser is unavailable
        return _fallback_pil_generator(group_title, formatted_users, timeframe_title)

def _fallback_pil_generator(group_title, users, timeframe_title):
    output_path = tempfile.mktemp(suffix=".png")
    img = Image.new("RGB", (1536, 1024), (5, 16, 46))
    draw = ImageDraw.Draw(img)

    def font(size, bold=True):
        p = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        return ImageFont.truetype(p, size) if os.path.exists(p) else ImageFont.load_default()

    draw.text((768, 80), "LEADERBOARD", font=font(60), fill=(255, 215, 0), anchor="mm")
    draw.text((768, 140), f"👑 Top Chatters of {group_title} ({timeframe_title}) 👑", font=font(28), fill=(255, 255, 255), anchor="mm")

    y = 220
    for idx, u in enumerate(users[:10], start=1):
        draw.text((300, y), f"#{idx} {u['name']}", font=font(24), fill=(255, 255, 255), anchor="lm")
        draw.text((1200, y), f"💬 {u['count']:,}", font=font(24), fill=(255, 220, 60), anchor="rm")
        y += 70

    img.save(output_path)
    return output_path
