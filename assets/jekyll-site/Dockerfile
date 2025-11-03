FROM ruby:3.2-slim

# Install dependencies
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /site

# Copy Gemfile
COPY Gemfile* ./

# Install gems
RUN bundle install

# Copy the rest of the site
COPY . .

# Expose port
EXPOSE 4000

# Run Jekyll
CMD ["bundle", "exec", "jekyll", "serve", "--host", "0.0.0.0", "--livereload"]
