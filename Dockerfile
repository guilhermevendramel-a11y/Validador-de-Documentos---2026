# ===============================
# BASE PYTHON + NEXT.JS
# ===============================
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# ===============================
# DIRETÓRIO
# ===============================
WORKDIR /app

# ===============================
# DEPENDÊNCIAS DO SISTEMA
# ===============================
RUN apt-get update && apt-get install -y \
    curl \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-por \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ===============================
# COPIA DEPENDENCIAS
# ===============================
COPY requirements.txt .
COPY package.json .

# ===============================
# INSTALA PYTHON + NODE
# ===============================
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN npm install

# ===============================
# COPIA APP
# ===============================
COPY . .
RUN npm run build

# ===============================
# PORTA
# ===============================
ENV PORT=8000
ENV PYTHON_BIN=python
EXPOSE 8000

# ===============================
# START
# ===============================
CMD ["npm", "run", "start"]
