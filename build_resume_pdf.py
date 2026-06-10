import re
from xhtml2pdf import pisa

html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page { margin: 0.55in 0.6in; size: letter; }
  body { font-family: Arial, sans-serif; font-size: 10pt; line-height: 1.4; color: #111; }
  .name { font-size: 20pt; font-weight: bold; text-align: center; margin: 0 0 3px 0; }
  .contact { text-align: center; font-size: 9.5pt; color: #333; margin: 0 0 10px 0; }
  h2 { font-size: 10.5pt; text-transform: uppercase; letter-spacing: 0.8px;
       border-bottom: 1.5px solid #111; padding-bottom: 1px; margin: 11px 0 5px 0; }
  .summary { font-size: 9.8pt; margin: 0 0 4px 0; }
  .edu-row { display: table; width: 100%; }
  .edu-left { display: table-cell; font-weight: bold; }
  .edu-right { display: table-cell; text-align: right; font-size: 9.5pt; color: #333; }
  .edu-sub { font-size: 9.5pt; margin: 1px 0 0 0; }
  .job-header { display: table; width: 100%; margin-top: 7px; }
  .job-left { display: table-cell; font-weight: bold; font-size: 10pt; }
  .job-right { display: table-cell; text-align: right; font-size: 9.5pt; color: #333; }
  .job-sub { display: table; width: 100%; }
  .job-sub-left { display: table-cell; font-style: italic; font-size: 9.5pt; }
  .job-sub-right { display: table-cell; text-align: right; font-style: italic; font-size: 9.5pt; color: #333; }
  ul { margin: 3px 0 4px 0; padding-left: 15px; }
  li { margin-bottom: 2px; font-size: 9.8pt; }
  .proj-title { font-weight: bold; font-size: 9.8pt; margin-top: 6px; }
  .proj-tech { font-style: italic; font-weight: normal; }
  .skill-row { font-size: 9.8pt; margin-bottom: 2px; }
  .skill-label { font-weight: bold; }
</style>
</head>
<body>

<div class="name">Basheer Khan</div>
<div class="contact">Minneapolis, MN &nbsp;|&nbsp; (651) 252-0785 &nbsp;|&nbsp; basheerkhan.43135@gmail.com &nbsp;|&nbsp; linkedin.com/in/basheerkhn</div>

<h2>Professional Summary</h2>
<p class="summary">Management Information Systems student with hands-on experience in data analytics, business intelligence,
and operations process improvement. Proficient in Python, SQL, Excel, and data visualization tools including Tableau and Power BI.
Experienced in applying analytical methods to drive business decisions, automate workflows, and communicate insights to
cross-functional stakeholders. Seeking an internship in Information Systems, Business Analysis, or Data Analytics to apply
technical and business skills in a professional environment.</p>

<h2>Education</h2>
<div class="edu-row">
  <div class="edu-left">Augsburg University</div>
  <div class="edu-right">Minneapolis, MN</div>
</div>
<div class="edu-sub">Bachelor of Science in Business Administration (B.S.B.A.) &mdash; Major: Management Information Systems</div>
<div class="edu-sub">Minors: Data Analytics, Computer Science &nbsp;&nbsp; GPA: 3.6/4.0 &nbsp;&nbsp; Expected May 2027</div>

<h2>Experience</h2>

<div class="job-header">
  <div class="job-left">Data Analytics Intern &mdash; Qualitative &amp; Quantitative Insights</div>
  <div class="job-right">May 2026 &ndash; Present</div>
</div>
<div class="job-sub">
  <div class="job-sub-left">Beats by Dre</div>
  <div class="job-sub-right">Remote</div>
</div>
<ul>
  <li>Analyzed consumer survey data in Python (Google Colab) to identify behavioral trends, brand preferences, and purchase motivations across Beats customer segments using pandas and NumPy for data cleaning and aggregation.</li>
  <li>Applied VADER sentiment analysis to open-ended survey responses, classifying feedback by emotional tone and brand attribute to surface actionable consumer insights for cross-functional business strategy discussions.</li>
  <li>Designed an interactive data visualization dashboard to present findings to the Global Consumer Insights team; communicated results clearly to non-technical stakeholders through structured presentations.</li>
  <li>Compiled a final report synthesizing quantitative and qualitative results, directly supporting senior leadership brand strategy and requirements gathering for future consumer research initiatives.</li>
</ul>

<div class="job-header">
  <div class="job-left">Operations Specialist</div>
  <div class="job-right">Apr 2022 &ndash; Mar 2024</div>
</div>
<div class="job-sub">
  <div class="job-sub-left">MetroCare Inc.</div>
  <div class="job-sub-right">St. Paul, MN</div>
</div>
<ul>
  <li>Managed scheduling and daily operations for a 4-person healthcare team, establishing workflow systems and process documentation that improved consistency and reduced coordination errors.</li>
  <li>Led systems implementation of a digital scheduling platform, transitioning from paper-based timesheets and reducing duplicate data entry while improving processing efficiency by an estimated 25&ndash;35%.</li>
  <li>Maintained DHS billing and payroll reconciliation records in Microsoft Excel, ensuring accurate pay periods and audit-ready documentation through database management and data integrity practices.</li>
  <li>Identified and resolved recurring billing discrepancies through systems analysis and client record restructuring, improving invoice accuracy and reducing payment delays.</li>
</ul>

<h2>Projects</h2>

<div class="proj-title">Brand Sentiment &amp; Survey Analysis &nbsp;<span class="proj-tech">| Python, VADER Sentiment, pandas, Matplotlib, Google Colab</span></div>
<ul>
  <li>Applied VADER sentiment scoring and data analysis techniques to customer survey responses, categorizing feedback by emotional tone and brand attribute to identify key factors driving repurchase intent.</li>
  <li>Produced structured data visualizations in Matplotlib covering sentiment distributions and attribute rankings, formatted as a leadership-ready business intelligence report.</li>
</ul>

<div class="proj-title">Operations Reporting Workbook &nbsp;<span class="proj-tech">| Excel, Pivot Tables, VLOOKUP, Conditional Formatting, Microsoft 365</span></div>
<ul>
  <li>Built a multi-tab Excel workbook consolidating scheduling, visit completion, and billing data across pay periods; used VLOOKUP and pivot tables to generate automated weekly accuracy summaries and KPI reports.</li>
  <li>Calculated pre- and post-adoption billing accuracy rates, documenting a measurable reduction in errors that supported a team-wide systems rollout decision through data-driven requirements analysis.</li>
</ul>

<div class="proj-title">Internship Job Tracker Dashboard &nbsp;<span class="proj-tech">| Python, REST APIs, HTML/CSS/JavaScript, GitHub Actions</span></div>
<ul>
  <li>Developed Python scripts using REST APIs to query job board platforms &mdash; Greenhouse, Lever, LinkedIn, and Workday &mdash; aggregating MN and Remote internship listings into a structured JSON database.</li>
  <li>Deployed a live business intelligence dashboard to GitHub Pages with automated hourly data refresh via GitHub Actions CI/CD pipeline; integrated a URL liveness checker to maintain data accuracy automatically.</li>
</ul>

<h2>Technical Skills</h2>
<div class="skill-row"><span class="skill-label">Languages:</span> Python, SQL, JavaScript, HTML/CSS</div>
<div class="skill-row"><span class="skill-label">Analytics &amp; BI:</span> Excel, Tableau, Power BI, Google Sheets, Google Colab, Data Visualization, Business Intelligence</div>
<div class="skill-row"><span class="skill-label">Libraries:</span> pandas, NumPy, Matplotlib</div>
<div class="skill-row"><span class="skill-label">Methods:</span> Systems Analysis, Business Analysis, Survey Analysis, Sentiment Analysis, KPI Reporting, Data Cleaning, Requirements Gathering, Process Documentation, Process Improvement, Cross-functional Collaboration</div>
<div class="skill-row"><span class="skill-label">Tools:</span> Git, GitHub, VS Code, REST APIs, Microsoft 365, Microsoft Office Suite, Canva</div>
<div class="skill-row"><span class="skill-label">Concepts:</span> Management Information Systems, Database Management, Agile Methodology, Information Technology, ERP Systems, Stakeholder Communication</div>

</body>
</html>"""

with open("basheer-khan-augsburg.pdf", "wb") as out:
    result = pisa.CreatePDF(html.encode("utf-8"), dest=out)

if result.err:
    print(f"Error: {result.err}")
else:
    import os
    size = os.path.getsize("basheer-khan-augsburg.pdf")
    print(f"PDF generated: basheer-khan-augsburg.pdf ({size:,} bytes)")
