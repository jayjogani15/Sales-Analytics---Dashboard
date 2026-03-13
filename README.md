# Sales Analytics Dashboard 🚀

The Sales Analytics Dashboard is a data-driven web application designed to analyze and visualize sales performance using Python, Flask, and data visualization libraries. The dashboard provides interactive charts and insights that help businesses understand revenue trends, regional performance, and overall sales growth.

## ✨ Features

- **Interactive UI**: Premium Dark and **Light Mode** themes with glassmorphism elements.
- **Dynamic Filtering**: Filter data in real-time by Region, Product, and custom Date Ranges.
- **Quick Date Presets**: Instantly filter data by Last 7 Days, Last 30 Days, or YTD.
- **Growth Indicators**: Automatically calculates and displays percentage growth vs the previous period.
- **Interactive Drill-downs**: Click on any Chart bar or pie slice to instantly filter the entire dashboard.
- **Rich Visualizations**: Interactive daily trend lines, product sales bar charts, and regional distribution pie charts using Plotly.js.
- **Advanced Data Table**: A highly customizable DataTables.js integration with live search, column sorting, and pagination.
- **Data Exporting**: 1-click downloads for **CSV**, **Excel**, and full-dashboard **PDF Reports**.
- **CSV Data Ingestion**: Seamlessly drag-and-drop or upload your sales records via CSV.
- **Responsive Design**: Fully mobile-responsive layout built with Bootstrap 5.

## 🛠️ Tech Stack

- **Backend**: Python 3, Flask, Pandas
- **Frontend**: HTML5, Vanilla CSS, JavaScript, Bootstrap 5
- **Data Visualization**: Plotly Python, Plotly.js
- **Table Management**: DataTables.js

## 🚀 How to Run Locally

1. **Clone the repository**:
   ```bash
   git clone https://github.com/jayjogani15/Sales-Analytics---Dashboard.git
   cd sales-dashboard
   ```

2. **Install dependencies**:
   Make sure you have Python installed. Then run:
   ```bash
   pip install flask pandas plotly werkzeug
   ```

3. **Start the server**:
   ```bash
   python app.py
   ```

4. **View the Dashboard**:
   Open your browser and navigate to `http://127.0.0.1:5000`

## 📊 CSV Format Requirement
Upload data in `.csv` format with at least the following columns:
- `Date` (e.g., YYYY-MM-DD)
- `Product`
- `Region`
- `Sales` (Numeric value)
