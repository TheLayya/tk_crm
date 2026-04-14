import uvicorn
import os
from app.core.config import settings

if __name__ == "__main__":
    port = int(os.environ.get('PORT', settings.PORT))
    uvicorn.run("app.main:app", host=settings.HOST, port=port, reload=False)
