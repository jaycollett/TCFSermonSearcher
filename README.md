# TCF Sermon Searcher

A Flask-based web application for searching sermon transcriptions, with AI-enhanced search capabilities, metrics tracking, and multilingual support.

## Features

- **Full-text Search**: Find specific topics, verses, or phrases across all sermons
- **Multilingual**: Support for English and Spanish content
- **Audio Playback**: Listen to the original sermon recordings
- **AI-Enhanced**: Optional AI-generated summaries, key quotes, and topic analysis
- **Category Filtering**: Filter sermons by category
- **Statistics**: Data visualization of sermon content
- **Search Metrics**: Track search queries and sermon access patterns
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

   - The `data` directory will contain the SQLite databases (sermons.db and metrics.db)
   - The `data/audiofiles` directory will store sermon audio files

4. **Prepare Database Files**

   Ensure the `data` directory contains a `sermons.db` file (even if empty). If it doesn't exist:

   ```sh
   touch data/sermons.db
   ```

   The application will automatically initialize the database schemas when it starts.

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

- **Backend**: Flask (Python 3.12)
- **Database**: SQLite with FTS5 for full-text search
- **Frontend**: Bootstrap, HTML/CSS/JavaScript
- **Translation**: Flask-Babel for internationalization
- **Visualization**: Matplotlib and WordCloud for statistics
- **Deployment**: Docker, Gunicorn
- **Analytics**: Custom metrics database for search and access tracking

## API Endpoints

The application provides several API endpoints for uploading, managing sermons, and accessing metrics:

- `POST /api/upload_sermon`: Upload a new sermon with audio
- `POST /api/ai_sermon_content`: Upload AI-generated content for a sermon
- `POST /api/update_stats`: Recalculate sermon statistics
- `GET /api/sermons`: Get a list of available sermons
- `GET /api/metrics`: Get search and access metrics data (requires admin auth)

All API endpoints require authentication using the `X-API-Token` header.

## Development

### Project Structure

```
/TCFSermonSearcher/
├── sermon_search/          # Main package
│   ├── __init__.py         # Package initialization
│   ├── app.py              # Application instance
│   ├── app_factory.py      # Flask app factory
│   ├── routes.py           # Route handlers
│   ├── database/           # Database models and operations
│   │   ├── __init__.py
│   │   ├── models.py       # Database models
│   │   └── init_metrics_db.py # Metrics database initialization
│   ├── static/             # Static files (CSS, JS, images)
│   ├── templates/          # HTML templates
│   ├── translations/       # Internationalization files
│   └── utils/              # Utility functions
│       ├── __init__.py
│       ├── security.py     # Security and visitor tracking
│       ├── sermons.py      # Sermon-related utilities
│       └── text.py         # Text processing utilities
├── build_utils/            # Build and setup tools
├── data/                   # Database and media files (not in git)
├── tests/                  # Test suite
├── app.py                  # Application entry point
├── config/                 # Configuration settings
├── requirements.txt        # Python dependencies
└── Dockerfile              # Docker configuration
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
   python -m nltk.downloader stopwords
   ```

3. **Set up environment variables**

   Create a `.env` file in the project root with the following variables:

   ```
   FLASK_APP=app.py
   FLASK_ENV=development
   DATABASE_PATH=data/sermons.db
   METRICS_DB_PATH=data/metrics.db
   AUDIOFILES_DIR=data/audiofiles
   SERMON_API_TOKEN=your-secure-token-here
   ```

4. **Download Bootstrap files locally**

   ```sh
   python build_utils/download_bootstrap.py
   ```

5. **Run the application**

   ```sh
   # Use the run script for development
   python run.py
   
   # Or use the rebuild and run script to refresh dependencies
   ./rebuild_and_run.sh
   ```

### Testing

Tests are written using pytest. To run the tests:

```sh
pytest
```

For specific test files:

```sh
pytest tests/test_routes.py
```

### Code Quality

- **Linting**: `pylint sermon_search`
- **Type checking**: `mypy sermon_search`
- **Formatting**: `black sermon_search`

### Translation

To update translations:

```sh
# Extract messages
pybabel extract -F build_utils/babel.cfg -o translations/messages.pot .

# Update translation files
pybabel update -i translations/messages.pot -d translations

# Compile translations
pybabel compile -d translations
```

Or use the utility script:

```sh
python build_utils/update_translations.py
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