import re

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if 'ref_html = ""' in line and start_idx == -1:
        start_idx = i
    elif 'st.info("No field photos recorded for this watershed yet.")' in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    # the target ends at the `else:` before the `st.info`
    # Let's find the `else:`
    while "else:" not in lines[end_idx - 1]:
        end_idx -= 1
    
    new_code = """                    ref_html = ""

                    if ref_dist is not None:
                        try:
                            ref_html += (
                                f"<div style='margin-top:4px;'>"
                                f"📏 Reference distance: {float(ref_dist):.1f} m"
                                f"</div>"
                            )
                        except (TypeError, ValueError):
                            pass

                    if ref_id is not None:
                        ref_html += (
                            f"<div style='margin-top:4px;'>"
                            f"🔎 Reference observation: #{ref_id}"
                            f"</div>"
                        )

                    verified_html = ""
                    if photo.get("verified"):
                        verified_html = (
                            "<div style='margin-top:6px; font-size:11px; "
                            "color:#166534; font-weight:600;'>"
                            "✓ Manually Verified"
                            "</div>"
                        )

                    verification_html = (
                        f"<div style='margin-top:8px; padding:8px; "
                        f"border-radius:7px; background:{v_bg}; "
                        f"color:{v_color}; font-size:11px; font-weight:600;'>"
                        f"{v_label}"
                        f"{ref_html}"
                        f"</div>"
                    )

                    st.markdown(
                        f\"\"\"
                        <div style="
                            border:1px solid #334155;
                            border-radius:10px;
                            padding:12px;
                            margin:6px 0;
                            border-left:4px solid {status_color};
                            background:rgba(30,41,59,0.6);
                        ">
                            <strong style="color:#f8fafc;">
                                {photo.get('type', 'Photo')}
                            </strong>

                            <br>
                            <span style="color:#94a3b8; font-size:12px;">
                                📍 {photo.get('lat', 0):.4f},
                                {photo.get('lon', 0):.4f}
                            </span>

                            <br>
                            <span style="color:#94a3b8; font-size:12px;">
                                📅 {photo.get('date', '')}
                            </span>

                            <br>
                            <span style="
                                background:{status_color};
                                color:white;
                                padding:2px 8px;
                                border-radius:8px;
                                font-size:11px;
                                font-weight:600;
                            ">
                                {photo.get('status', '')}
                            </span>

                            {verification_html}

                            {verified_html}

                            <br>
                            <span style="
                                display:block;
                                margin-top:6px;
                                font-size:12px;
                                color:#cbd5e1;
                            ">
                                {photo.get('description', '')[:60]}
                            </span>
                        </div>
                        \"\"\",
                        unsafe_allow_html=True,
                    )
"""
    lines[start_idx:end_idx - 1] = [new_code]
    
    with open("app.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Fixed app.py")
else:
    print(f"Could not find start/end indices: start={start_idx}, end={end_idx}")
