"""
Sales Data Analytics Dashboard
================================
A Flask web application for uploading, analyzing, and visualizing sales data.

Author: Sales Dashboard App
Tech Stack: Flask, Pandas, Plotly
"""

import os
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "sales_dashboard_secret_key_2024"

# Folder where uploaded CSVs are temporarily saved
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ALLOWED_EXTENSIONS = {"csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB limit

# Enterprise Global Configuration
REVENUE_GOAL = 1500000  # $1.5M Goal

# Required columns in the uploaded CSV
REQUIRED_COLUMNS = {"Date", "Product", "Region", "Sales"}

# Make sure the data folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database Configuration
# Fallback to local SQLite if DATABASE_URL is not provided (e.g., local dev)
db_url = os.environ.get('DATABASE_URL', 'sqlite:///app.db')

# Fix for Render/Heroku PostgreSQL URLs: SQLAlchemy requires 'postgresql://'
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)

class SalesRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, index=True)
    product = db.Column(db.String(100), nullable=False)
    region = db.Column(db.String(100), nullable=False)
    sales = db.Column(db.Float, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create DB and Default Admin
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        hashed_pw = generate_password_hash('admin123', method='scrypt')
        admin_user = User(username='admin', password_hash=hashed_pw)
        db.session.add(admin_user)
        db.session.commit()
        print("Default Admin user created (admin / admin123)")


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def load_dataframe(filepath: str):
    try:
        # Try reading with robust fallback encodings
        try:
            df = pd.read_csv(filepath, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(filepath, encoding='utf-8-sig')
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, encoding='latin1')
    except Exception as exc:
        return None, f"Could not read file: {exc}"

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Check required columns (case-insensitive)
    col_map = {c.lower(): c for c in df.columns}
    normalized = {}
    missing = []
    for req in REQUIRED_COLUMNS:
        if req.lower() in col_map:
            normalized[col_map[req.lower()]] = req
        else:
            missing.append(req)

    if missing:
        return None, f"Missing required columns: {', '.join(sorted(missing))}"

    # Rename to standard names if needed
    df = df.rename(columns=normalized)

    # Drop rows where all essential columns are NaN
    df.dropna(subset=["Date", "Product", "Region", "Sales"], how="all", inplace=True)

    if df.empty:
        return None, 

    # Parse Date column
    try:
        df["Date"] = pd.to_datetime(df["Date"])
    except Exception:
        return None, 

    # Ensure Sales is numeric
    df["Sales"] = pd.to_numeric(df["Sales"], errors="coerce")
    df.dropna(subset=["Sales"], inplace=True)

    if df.empty:
        return None, "No valid numeric values found in the 'Sales' column."

    return df, None


def get_db_dataframe():
    try:
        df = pd.read_sql("SELECT date as Date, product as Product, region as Region, sales as Sales FROM sales_record", con=db.engine)
        if df.empty:
            return None, "Database is empty."
        df["Date"] = pd.to_datetime(df["Date"])
        return df, None
    except Exception as e:
        return None, str(e)


def to_chart_json(fig) -> str:
    return pio.to_json(fig)


def compute_kpis(df: pd.DataFrame, full_df: pd.DataFrame = None) -> dict:
    total_sales = df["Sales"].sum() if not df.empty else 0
    goal_progress_pct = min((total_sales / REVENUE_GOAL) * 100, 100) if REVENUE_GOAL > 0 else 0
    
    avg_sales = df["Sales"].mean() if not df.empty else 0
    best_product = df.groupby("Product")["Sales"].sum().idxmax() if not df.empty else "-"
    top_region = df.groupby("Region")["Sales"].sum().idxmax() if not df.empty else "-"
    total_products = df["Product"].nunique()
    total_records = len(df)

    # Calculate Growth Indicators
    sales_growth = 0
    sales_growth_str = "-"
    sales_growth_class = "text-muted"

    if full_df is not None and not full_df.empty and not df.empty:
        # Calculate days in current filtered period
        days_in_current = (df["Date"].max() - df["Date"].min()).days + 1
        if days_in_current > 0:
            prev_end = df["Date"].min() - pd.Timedelta(days=1)
            prev_start = prev_end - pd.Timedelta(days=days_in_current - 1)
            # Find sales in the comparative prior period
            prev_df = full_df[(full_df["Date"] >= prev_start) & (full_df["Date"] <= prev_end)]
            prev_sales = prev_df["Sales"].sum()
            
            if prev_sales > 0:
                sales_growth = ((total_sales - prev_sales) / prev_sales) * 100
                sales_growth_str = f"↑ {sales_growth:.1f}%" if sales_growth >= 0 else f"↓ {abs(sales_growth):.1f}%"
                sales_growth_class = "text-emerald" if sales_growth >= 0 else "text-danger"

    # Generate Smart Insights
    insights = []
    if total_sales > 0:
        top_p_sales = df.groupby("Product")["Sales"].sum().max()
        pct_p = (top_p_sales / total_sales) * 100
        insights.append(f"⭐ <b>{best_product}</b> is your top product, driving <b>{pct_p:.1f}%</b> of revenue.")
        
        top_r_sales = df.groupby("Region")["Sales"].sum().max()
        pct_r = (top_r_sales / total_sales) * 100
        insights.append(f"🌍 The <b>{top_region}</b> region leads sales with <b>{pct_r:.1f}%</b> of the total.")
        
        if sales_growth_str != "-":
            direction = "grown by" if sales_growth >= 0 else "declined by"
            insights.append(f"📈 Sales have <b>{direction} {abs(sales_growth):.1f}%</b> compared to the previous period.")
    else:
        insights.append("No data available to generate insights.")

    return {
        "total_sales": f"${total_sales:,.2f}",
        "avg_sales": f"${avg_sales:,.2f}",
        "best_product": best_product,
        "top_region": top_region,
        "total_products": total_products,
        "total_records": total_records,
        "sales_growth": sales_growth_str,
        "sales_growth_class": sales_growth_class,
        "insights": insights,
        "revenue_goal": f"${REVENUE_GOAL:,.0f}",
        "goal_progress_pct": goal_progress_pct
    }


def build_bar_chart(df: pd.DataFrame) -> str:
    product_sales = (
        df.groupby("Product")["Sales"]
        .sum()
        .reset_index()
        .sort_values("Sales", ascending=False)
    )

    fig = go.Figure(
        go.Bar(
            x=product_sales["Product"],
            y=product_sales["Sales"],
            marker=dict(
                color="#22d3ee", # Cyan to match the trend line theme
                line=dict(color="rgba(255,255,255,0.1)", width=1),
                opacity=0.85
            ),
            text=[f"${v:,.0f}" for v in product_sales["Sales"]],
            textposition="outside",
            textfont=dict(color="#e2e8f0", size=11),
            hoverinfo="y+text",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#cbd5e1", family="Inter, sans-serif"),
        xaxis=dict(
            showgrid=False, 
            zeroline=False, 
            color="#94a3b8",
            tickfont=dict(size=11)
        ),
        yaxis=dict(
            showgrid=True, 
            gridcolor="rgba(100,116,139,0.2)", 
            zeroline=False,
            color="#94a3b8", 
            tickprefix="$",
            rangemode="tozero" # Ensure it starts at 0
        ),
        margin=dict(t=30, b=40, l=60, r=20),
        height=380,
        bargap=0.5,
        hoverlabel=dict(
            bgcolor="#0f172a",
            font_size=13,
            font_color="#ffffff",
            font_family="Inter, sans-serif"
        )
    )
    return to_chart_json(fig)


def build_pie_chart(df: pd.DataFrame) -> str:
    
    region_sales = df.groupby("Region")["Sales"].sum().reset_index().sort_values("Sales", ascending=False)
    colors = ["#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#a855f7", "#ef4444"]

    fig = go.Figure(
        go.Pie(
            labels=region_sales["Region"],
            values=region_sales["Sales"],
            hole=0.55,
            marker=dict(
                colors=colors[:len(region_sales)],
                line=dict(color="#0f172a", width=2)
            ),
            textinfo="label+percent",
            textfont=dict(size=13),
        )
    )
    fig.update_layout(
        title=dict(text="Sales by Region", font=dict(size=18, color="#e2e8f0"), x=0.02),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#cbd5e1", family="Inter, sans-serif"),
        showlegend=True,
        legend=dict(font=dict(color="#cbd5e1"), bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=60, b=20, l=20, r=20),
        height=380,
    )
    return to_chart_json(fig)


def build_line_chart(df: pd.DataFrame) -> str:
    dfc = df.copy()
    
    # Aggregating by Day instead of Week to provide more dynamic/variable trends
    dfc["DateStr"] = dfc["Date"].dt.strftime("%Y-%m-%d")
    daily = dfc.groupby("DateStr")["Sales"].sum().reset_index().sort_values("DateStr")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily["DateStr"],
            y=daily["Sales"],
            mode="lines+markers",
            name="Sales",
            line=dict(
                color="#22d3ee", 
                width=3, 
                shape="spline",
                smoothing=1.3
            ),
            marker=dict(
                size=4,
                color="#22d3ee",
                opacity=0.8
            ),
            fill="tozeroy",
            fillcolor="rgba(34, 211, 238, 0.08)",
            hovertemplate="Sales: $%{y:,.0f}<extra></extra>",
        )
    )
    # Add a subtle glow effect (no hover)
    fig.add_trace(
        go.Scatter(
            x=daily["DateStr"],
            y=daily["Sales"],
            mode="lines",
            line=dict(color="rgba(34, 211, 238, 0.15)", width=8, shape="spline"),
            hoverinfo="skip",
            showlegend=False
        )
    )
    fig.update_layout(
        title=dict(text="Daily Sales Trend", font=dict(size=18, color="#e2e8f0"), x=0.02),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#cbd5e1", family="Inter, sans-serif"),
        xaxis=dict(
            showgrid=False, 
            zeroline=False, 
            tickangle=-30, 
            color="#94a3b8",
            showspikes=False # Remove the "big white line" (spikes)
        ),
        yaxis=dict(
            showgrid=True, 
            gridcolor="rgba(100,116,139,0.25)", 
            zeroline=False,
            color="#94a3b8", 
            tickprefix="$",
            showspikes=False
        ),
        margin=dict(t=60, b=70, l=70, r=20),
        height=380,
        hovermode="closest", # Removes the unified vertical line
        hoverlabel=dict(
            bgcolor="#0f172a", # Dark black-blue background
            font_size=13,
            font_color="#ffffff", # White text
            font_family="Inter, sans-serif",
            bordercolor="#1e293b"
        )
    )
    return to_chart_json(fig)

@app.route("/")
def index():
    """Redirect root to the dashboard."""
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
   
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)

        file = request.files["file"]

        if file.filename == "":
            flash("No file selected. Please choose a CSV file.", "warning")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Invalid file type. Only CSV files are accepted.", "danger")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], "uploaded_" + filename)
        file.save(filepath)

        # Validate the file content
        df, error = load_dataframe(filepath)
        if error:
            try:
                os.remove(filepath)  
            except OSError:
                pass
            flash(f"Upload failed: {error}", "danger")
            return redirect(request.url)
            
        # Bulk-insert into database
        df_sql = df.copy()
        df_sql.columns = df_sql.columns.str.lower()
        df_sql.to_sql('sales_record', con=db.engine, if_exists='replace', index=False)
        
        session["uploaded_file"] = filepath
        flash("File uploaded and data imported to SQL Database successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("upload.html")


@app.route("/dashboard")
@login_required
def dashboard():
    
    # Fetch from SQLite database
    df, error = get_db_dataframe()

    if error:
        # Fall back to the bundled sample dataset if DB is empty
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], "sales.csv")
        df, error = load_dataframe(filepath)
        if error:
            flash(f"Error reading seed data: {error}", "danger")
            return redirect(url_for("upload"))
            
        # Seed DB for next time
        df_sql = df.copy()
        df_sql.columns = df_sql.columns.str.lower()
        df_sql.to_sql('sales_record', con=db.engine, if_exists='replace', index=False)

    # Compute KPIs
    kpis = compute_kpis(df, df)

    # Generate Plotly chart JSON (each function works on its own copy)
    bar_chart_json = build_bar_chart(df)
    pie_chart_json = build_pie_chart(df)
    line_chart_json = build_line_chart(df)

    # Prepare table data (most recent 25 rows sorted by date descending)
    table_df = (
        df[["Date", "Product", "Region", "Sales"]]
        .sort_values("Date", ascending=False)
        .head(25)
        .copy()
    )
    table_df["Date"] = table_df["Date"].dt.strftime("%d %b %Y")
    table_df["Sales"] = table_df["Sales"].apply(lambda x: f"${x:,.2f}")
    table_data = table_df.to_dict(orient="records")

    # Get unique regions and products for the filter dropdowns
    regions = sorted(df["Region"].dropna().unique().tolist())
    products = sorted(df["Product"].dropna().unique().tolist())

    return render_template(
        "dashboard.html",
        kpis=kpis,
        bar_chart_json=bar_chart_json,
        pie_chart_json=pie_chart_json,
        line_chart_json=line_chart_json,
        table_data=table_data,
        filename="SQLite Database",
        regions=regions,
        products=products,
    )

@app.route("/api/data")
@login_required
def api_data():
    """
    API endpoint that returns filtered KPIs, Charts, and Table data in JSON.
    Query Params: region, product, start_date, end_date
    """
    df, error = get_db_dataframe()
    if error:
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], "sales.csv")
        df, error = load_dataframe(filepath)
        if error:
            return jsonify({"error": error}), 400

    # Apply filters
    full_df = df.copy()
    region = request.args.get("region")
    product = request.args.get("product")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if region and region != "All":
        df = df[df["Region"] == region]
    if product and product != "All":
        df = df[df["Product"] == product]
    if start_date:
        df = df[df["Date"] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df["Date"] <= pd.to_datetime(end_date)]

    # If the filter resulted in an empty dataframe, return empty structures safely
    if df.empty:
        empty_kpis = {
            "total_sales": "$0.00", "avg_sales": "$0.00", 
            "best_product": "-", "top_region": "-", 
            "total_products": 0, "total_records": 0,
            "sales_growth": "-", "sales_growth_class": "text-muted",
            "insights": ["No data available to generate insights."],
            "revenue_goal": f"${REVENUE_GOAL:,.0f}",
            "goal_progress_pct": 0
        }
        empty_fig = pio.to_json(go.Figure(layout=dict(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#cbd5e1", family="Inter, sans-serif"),
            xaxis=dict(showgrid=False, zeroline=False), yaxis=dict(showgrid=False, zeroline=False),
            annotations=[dict(text="No data matching filters", xref="paper", yref="paper", showarrow=False, font=dict(size=16))]
        )))
        return jsonify({
            "kpis": empty_kpis,
            "charts": {"bar": empty_fig, "pie": empty_fig, "line": empty_fig},
            "table": []
        })

    kpis = compute_kpis(df, full_df)
    bar_chart = build_bar_chart(df)
    pie_chart = build_pie_chart(df)
    line_chart = build_line_chart(df)

    # Prepare table data for DataTables
    table_df = df[["Date", "Product", "Region", "Sales"]].copy()
    table_df["Date"] = table_df["Date"].dt.strftime("%Y-%m-%d") # Use standard YYYY-MM-DD for easier sorting by DataTables
    table_df["Sales"] = table_df["Sales"].apply(lambda x: f"${x:,.2f}")
    table_data = table_df.to_dict(orient="records")

    return jsonify({
        "kpis": kpis,
        "charts": {
            "bar": bar_chart,
            "pie": pie_chart,
            "line": line_chart
        },
        "table": table_data
    })


@app.route("/reset")
@login_required
def reset():
    """Clear the uploaded file, wipe the database table, and return to upload page."""
    filepath = session.pop("uploaded_file", None)
    if filepath and os.path.exists(filepath) and "uploaded_" in os.path.basename(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
            
    try:
        db.session.execute(db.text("DELETE FROM sales_record"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        
    flash("Database wiped and session cleared. Upload a new file to get started.", "info")
    return redirect(url_for("upload"))


# ---------------------------------------------------------------------------
# Automated Email Reports (APScheduler)
# ---------------------------------------------------------------------------
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

def generate_and_save_email_report():
    with app.app_context():
        df, error = get_db_dataframe()
        if error or df is None or df.empty:
            print("Email Scheduler: No data available to generate report.")
            return

        kpis = compute_kpis(df, df)
        
        # Build a beautiful HTML Email Template
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4f46e5;">SalesFlow Analytics Report</h2>
                <p>Here is your automated performance summary as of <b>{datetime.now().strftime('%d %b %Y, %H:%M')}</b>:</p>
                <div style="background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <ul style="list-style: none; padding: 0;">
                        <li style="margin-bottom: 10px;"><b>Total Sales:</b> {kpis['total_sales']}</li>
                        <li style="margin-bottom: 10px;"><b>Goal Progress:</b> {kpis['goal_progress_pct']:.1f}%</li>
                        <li style="margin-bottom: 10px;"><b>Best Product:</b> {kpis['best_product']}</li>
                        <li style="margin-bottom: 10px;"><b>Top Region:</b> {kpis['top_region']}</li>
                    </ul>
                </div>
                <h3 style="color: #4f46e5; margin-top: 20px;">AI Insights</h3>
                <ul>
                    {''.join([f'<li>{insight}</li>' for insight in kpis['insights']])}
                </ul>
                <p style="margin-top: 30px; font-size: 12px; color: #94a3b8;">
                    This is an automated message from the SalesFlow APScheduler background job.
                </p>
            </body>
        </html>
        """
        
        # Save to local file to simulate sending an email
        report_path = os.path.join(app.config["UPLOAD_FOLDER"], "latest_email_report.html")
        with open(report_path, "w", encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"[{datetime.now().strftime('%X')}] APScheduler: Email report generated successfully at {report_path}")

# Initialize the scheduler
try:
    generate_and_save_email_report() # Run once immediately on startup
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=generate_and_save_email_report, trigger="interval", minutes=1)
    scheduler.start()
except Exception as e:
    print(f"Failed to start APScheduler: {e}")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Get port from environment variable for cloud deployment (Render, Heroku, etc.)
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print(f"  Sales Analytics Dashboard")
    print(f"  Running at: http://0.0.0.0:{port}")
    print("=" * 60)
    # Turn off debug mode in production for security, or keep it manageable
    app.run(host="0.0.0.0", port=port, debug=True)
