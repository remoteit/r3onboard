# Use an official python image as a parent image
FROM python:3-bookworm

# Use bash as the default shell
SHELL [ "/bin/bash", "-c" ]

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set the working directory
WORKDIR /app

# Add poetry to the PATH
ENV PATH="${PATH}:/root/.local/bin" 

# Don't overwrite the virtualenv of the project
ENV POETRY_VIRTUALENVS_IN_PROJECT=false 

# Run the tests and install dependencies on container start
CMD ["/bin/sh", "-c", "poetry install && poetry run pytest"]
