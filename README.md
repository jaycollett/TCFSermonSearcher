# TCFSermonSearcher

## Overview
TCFSermonSearcher is a web application built with Python and Flask to help users quickly find past sermons using keyword-based searches. This tool enhances sermon accessibility, allowing users to search for specific messages based on words, phrases, and filters like date, speaker, or series.

## Features

- **Keyword Search** – Locate sermons containing specific words or phrases.
- **Advanced Filtering** – Narrow results by date range, speaker, or sermon series.
- **User-Friendly Interface** – Simple and intuitive design for easy navigation.
- **Fast & Efficient** – Optimized search functionality for quick results.

## Installation

To set up TCFSermonSearcher locally, follow these steps:

1. **Clone the Repository**
   ```sh
   git clone https://github.com/jaycollett/TCFSermonSearcher.git
   ```
2. **Navigate to the Project Directory**
   ```sh
   cd TCFSermonSearcher
   ```
3. **Create and Activate a Virtual Environment**
   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
4. **Install Dependencies**
   ```sh
   pip install -r requirements.txt
   ```
5. **Configure Environment Variables**
   - Create a `.env` file in the root directory.
   - Add necessary configuration settings based on your environment.
6. **Run Database Migrations (if applicable)**
   ```sh
   flask db upgrade
   ```
7. **Start the Application**
   ```sh
   flask run
   ```
8. **Access the Application**
   - Open your browser and go to: `http://localhost:5000`

## Usage

1. Enter a keyword or phrase in the search bar.
2. Apply filters if needed (date, speaker, sermon series, etc.).
3. View and access the relevant sermon content.

## Contributing

Contributions are welcome! Follow these steps to contribute:

1. **Fork the Repository** – Click the "Fork" button on GitHub.
2. **Create a New Branch**
   ```sh
   git checkout -b feature/YourFeatureName
   ```
3. **Make Your Changes** – Implement your feature or fix.
4. **Commit Your Changes**
   ```sh
   git commit -m "Add feature: YourFeatureName"
   ```
5. **Push to Your Fork**
   ```sh
   git push origin feature/YourFeatureName
   ```
6. **Submit a Pull Request** – Go to the original repository and open a pull request.
