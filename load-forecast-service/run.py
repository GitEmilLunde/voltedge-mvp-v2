from app import create_app
from app.services.forecast_engine import load_model

app = create_app()

# Indlæs ML-model ved service-start (én gang)
with app.app_context():
    load_model()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
