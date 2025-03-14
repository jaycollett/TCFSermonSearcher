# TCF Sermon Searcher

A Flask-based web application for searching sermon transcriptions, with AI-enhanced search capabilities and multilingual support.

## Features

- **Full-text Search**: Find specific topics, verses, or phrases across all sermons
- **Multilingual**: Support for English and Spanish content
- **Audio Playback**: Listen to the original sermon recordings
- **AI-Enhanced**: Optional AI-generated summaries, key quotes, and topic analysis
- **Category Filtering**: Filter sermons by category
- **Statistics**: Data visualization of sermon content
- **Mobile Friendly**: Responsive design works on all devices

## Running with Docker

The recommended way to run TCF Sermon Searcher is via Docker. Follow these steps:

1. **Clone the Repository**

   ```sh
   git clone https://github.com/jaycollett/TCFSermonSearcher.git
   ```

2. **Navigate to the Project Directory**

   ```sh
   cd TCFSermonSearcher
   ```

3. **Create Required Directories**

   The application requires specific directories for storing data. Create them with:

   ```sh
   mkdir -p data/audiofiles
   ```

   - The `data` directory will contain the SQLite database
   - The `data/audiofiles` directory will store sermon audio files

4. **Prepare Database File**

   Ensure the `data` directory contains a `sermons.db` file (even if empty). If it doesn't exist:

   ```sh
   touch data/sermons.db
   ```

   The application will automatically initialize the database schema when it starts.

5. **Build the Docker Image**

   ```sh
   docker build -t sermon-searcher .
   ```

6. **Run the Application in a Docker Container**

   ```sh
   docker run -d -p 5000:5000 \
     -v $(pwd)/data:/data \
     -e SERMON_API_TOKEN=your-secure-token \
     -e FLASK_ENV=production \
     --name sermon-searcher \
     sermon-searcher
   ```

   This command:
   - Maps port 5000 from the container to your host
   - Mounts the local `data` directory to `/data` in the container
   - Sets required environment variables
   - Names the container "sermon-searcher"

7. **Access the Application**

   Open your browser and go to: `http://localhost:5000`

## Technology Stack

- **Backend**: Flask (Python)
- **Database**: SQLite with FTS5 for full-text search
- **Frontend**: Bootstrap, HTML/CSS/JavaScript
- **Translation**: Flask-Babel for internationalization
- **Visualization**: Matplotlib and WordCloud for statistics
- **Deployment**: Docker, Gunicorn

## API Endpoints

The application provides several API endpoints for uploading and managing sermons:

- `POST /api/upload_sermon`: Upload a new sermon with audio
- `POST /api/ai_sermon_content`: Upload AI-generated content for a sermon
- `POST /api/update_stats`: Recalculate sermon statistics
- `GET /api/sermons`: Get a list of available sermons

All API endpoints require authentication using the `X-API-Token` header.

## Development

### Project Structure

```
/TCFSermonSearcher/
├── sermon_search/          # Main package
│   ├── __init__.py         # Package initialization
│   ├── app_factory.py      # Flask app factory
│   ├── routes.py           # Route handlers
│   ├── api/                # API endpoints
│   ├── database/           # Database models and operations
│   └── utils/              # Utility functions
├── templates/              # HTML templates
├── static/                 # Static files (CSS, JS, images)
├── translations/           # Internationalization files
├── data/                   # Database and media files
├── tests/                  # Test suite
├── app.py                  # Application entry point
├── config/                 # Configuration settings
├── requirements.txt        # Python dependencies
└── .env                    # Environment variables
```

### Setup Development Environment

1. **Create a virtual environment**

   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**

   ```sh
   pip install -r requirements.txt
   ```

3. **Set up environment variables**

   ```sh
   cp .env.example .env
   # Edit .env file to set your environment-specific values
   ```

4. **Download Bootstrap files locally**

   ```sh
   python download_bootstrap.py
   ```

5. **Run the application**

   ```sh
   # Use the run script for development
   python run.py
   
   # Or make it executable and run it directly
   chmod +x run.py
   ./run.py
   ```

### Testing

Tests are written using pytest. To run the tests:

```sh
pytest
```

### Code Quality

- **Linting**: `pylint sermon_search`
- **Type checking**: `mypy sermon_search`
- **Formatting**: `black sermon_search`

### Translation

To update translations:

```sh
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
pybabel compile -d translations
```

### Building and Pushing New Docker Images

To build and push a new version to Docker Hub:

```sh
docker build -t yourusername/sermon-searcher:latest .
docker push yourusername/sermon-searcher:latest
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request
