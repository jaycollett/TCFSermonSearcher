# TCFSermonSearcher

## Overview
TCFSermonSearcher is a web application built with Python and Flask to help users quickly find past sermons using keyword-based searches. This tool enhances sermon accessibility, allowing users to search for specific messages based on words, phrases, and full sentences.

## Features

- **Keyword Search** – Locate sermons containing specific words or phrases.
- **User-Friendly Interface** – Simple and intuitive design for easy navigation.
- **Fast & Efficient** – Optimized search functionality for quick results.

## Running with Docker

The recommended way to run TCFSermonSearcher is via Docker. Follow these steps:

1. **Clone the Repository**
   ```sh
   git clone https://github.com/jaycollett/TCFSermonSearcher.git
   ```
2. **Navigate to the Project Directory**
   ```sh
   cd TCFSermonSearcher
   ```
3. **Build the Docker Image**
   ```sh
   docker build -t tcfs-sermon-searcher .
   ```
4. **Run the Application in a Docker Container**
   ```sh
   docker run -d -p 5000:5000 --name tcfs-sermon-searcher tcfs-sermon-searcher
   ```
5. **Access the Application**
   - Open your browser and go to: `http://localhost:5000`

## Usage

1. Enter a keyword or phrase in the search bar.
2. View and access the relevant sermon content.

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
