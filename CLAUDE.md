# TCF Sermon Searcher - Development Guide

## Development Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the example environment file:
```bash
cp .env.example .env
```

4. Run the application:
```bash
python app.py
```

## Common Commands

### Run the application
```bash
python app.py
```

### Run with Gunicorn (production)
```bash
gunicorn --bind 0.0.0.0:5000 app:app
```

### Run tests
```bash
pytest
```

### Lint the code
```bash
pylint sermon_search
```

### Type checking
```bash
mypy sermon_search
```

### Format code
```bash
black sermon_search
```

### Update translations
```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
pybabel compile -d translations
```

## Project Structure

```
/TCFSermonSearcher/
├── sermon_search/          # Main package
│   ├── __init__.py         # Package initialization
│   ├── app_factory.py      # Flask app factory
│   ├── routes.py           # UI route handlers
│   ├── api/                # API endpoints
│   │   ├── __init__.py     # API blueprint definition
│   │   └── routes.py       # API route handlers
│   ├── database/           # Database models and operations
│   │   ├── __init__.py     # Database package exports
│   │   └── models.py       # Database models and functions
│   └── utils/              # Utility functions
│       ├── __init__.py     # Utility package exports
│       ├── security.py     # Security-related utilities
│       ├── sermons.py      # Sermon-related utilities
│       └── text.py         # Text processing utilities
├── templates/              # HTML templates
├── static/                 # Static files (CSS, JS, images)
│   ├── css/                # CSS files including Bootstrap
│   ├── js/                 # JavaScript files including Bootstrap
│   └── images/             # Image assets
├── translations/           # Internationalization files
├── data/                   # Database and media files
│   └── audiofiles/         # Sermon audio recordings
├── tests/                  # Test suite
├── app.py                  # Application entry point
├── run.py                  # Development server script
├── config/                 # Configuration settings
├── download_bootstrap.py   # Script to download Bootstrap locally
├── update_translations.py  # Script to update translations
├── requirements.txt        # Python dependencies
└── .env                    # Environment variables
```

## Database Schema

### sermons
- id: Primary key
- sermon_title: Title of the sermon
- transcription: Full text transcription
- transcription_timings: Optional timing data
- audiofilename: Audio file name
- sermon_guid: Unique identifier (UUID)
- language: Language code (en, es)
- categories: Comma-separated categories
- insert_date: Creation timestamp
- church: Church identifier

### sermons_fts
- Full-text search virtual table for sermons

### ai_sermon_content
- id: Primary key
- sermon_guid: Foreign key to sermons
- ai_summary: AI-generated summary
- ai_summary_es: Spanish summary
- bible_books: Referenced Bible books
- key_quotes: Important quotes
- topics: Sermon topics
- sentiment: Sentiment analysis
- sermon_style: Style analysis
- status: Processing status

### stats_for_nerds
- Statistics about the sermon database

### ip_bans
- Security table for tracking API abuse

## API Endpoints

The application provides the following API endpoints:

### GET /api/sermons
- Returns a list of available sermons
- Takes optional `page` parameter for pagination
- Returns JSON array of sermon objects

### POST /api/upload_sermon
- Uploads a new sermon with audio file
- Requires authentication via `X-API-Token` header
- Form parameters:
  - SermonGUID: Unique identifier
  - SermonTitle: Title of the sermon
  - Transcription: Full text transcription
  - Language: Language code (en, es)
  - Categories: Comma-separated list of categories
  - Church: Church identifier
  - TranscriptionTimings: Optional timing data
  - audiofile: MP3 file upload

### POST /api/ai_sermon_content
- Uploads AI-generated content for a sermon
- Requires authentication via `X-API-Token` header
- JSON payload with sermon_guid and AI content fields

### POST /api/update_stats
- Updates statistics about the sermon database
- Requires authentication via `X-API-Token` header
- Generates visualizations and calculates word counts

## Frontend Assets

### Bootstrap
The application uses Bootstrap for styling and JavaScript functionality. The Bootstrap files are:
- Stored locally in `/static/css/bootstrap.min.css` and `/static/js/bootstrap.bundle.min.js`
- Have a CDN fallback mechanism in case the local files aren't available
- Can be updated by running `python download_bootstrap.py`

This approach improves performance by:
1. Reducing external HTTP requests
2. Eliminating dependency on CDN availability
3. Allowing the site to work even without internet access