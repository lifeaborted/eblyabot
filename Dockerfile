FROM public.ecr.aws/lambda/python:3.11

# Установка ffmpeg из статической сборки
RUN yum update -y && \
    yum install -y wget tar xz && \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar xvf ffmpeg-release-amd64-static.tar.xz && \
    mv ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ && \
    mv ffmpeg-*-amd64-static/ffprobe /usr/local/bin/ && \
    rm -rf ffmpeg-* && \
    yum remove -y wget tar xz && \
    yum clean all && \
    rm -rf /var/cache/yum

# Копирование requirements.txt и установка зависимостей
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Копирование всех файлов проекта
COPY bot.py database.py downloader.py ${LAMBDA_TASK_ROOT}/

# Создание директорий для данных
RUN mkdir -p ${LAMBDA_TASK_ROOT}/downloads ${LAMBDA_TASK_ROOT}/data

# Установка рабочей директории
WORKDIR ${LAMBDA_TASK_ROOT}

# Переопределяем ENTRYPOINT и CMD для обычного ботика
ENTRYPOINT []
CMD ["python", "-u", "bot.py"]
