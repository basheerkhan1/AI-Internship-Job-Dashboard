import markdown
from xhtml2pdf import pisa

with open("cv.md", "r", encoding="utf-8") as f:
    md_content = f.read()

html_body = markdown.markdown(md_content, extensions=["tables"])

full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
      margin: 0.6in 0.65in 0.6in 0.65in;
      size: letter;
  }}
  body {{
      font-family: Helvetica, Arial, sans-serif;
      font-size: 10.5pt;
      line-height: 1.45;
      color: #111;
  }}
  h1 {{
      font-size: 20pt;
      margin: 0 0 2px 0;
  }}
  h1 + p {{
      font-size: 9.5pt;
      color: #444;
      margin: 0 0 10px 0;
  }}
  h2 {{
      font-size: 11pt;
      text-transform: uppercase;
      border-bottom: 1.5px solid #111;
      padding-bottom: 2px;
      margin: 14px 0 5px 0;
  }}
  h3 {{
      font-size: 10.5pt;
      margin: 8px 0 0 0;
  }}
  p {{
      margin: 2px 0 4px 0;
  }}
  ul {{
      margin: 2px 0 4px 0;
      padding-left: 16px;
  }}
  li {{
      margin-bottom: 2px;
  }}
  hr {{
      border-top: 1px solid #ccc;
      margin: 8px 0;
  }}
</style>
</head>
<body>{html_body}</body>
</html>"""

with open("basheer-khan-augsburg.pdf", "wb") as out:
    result = pisa.CreatePDF(full_html.encode("utf-8"), dest=out)

if result.err:
    print(f"Error generating PDF: {result.err}")
else:
    print("PDF generated: basheer-khan-augsburg.pdf")
