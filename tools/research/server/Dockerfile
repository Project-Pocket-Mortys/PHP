FROM php:8.3-apache@sha256:f8506a19d79cad7fcf0c8049f1ed2208824961018fdc10bd80f324094dcd36bd
RUN docker-php-ext-install pdo_mysql && a2enmod rewrite headers \
    && sed -i 's/CustomLog .*/CustomLog \/proc\/self\/fd\/1 research/' /etc/apache2/sites-available/000-default.conf
COPY research.conf /etc/apache2/conf-enabled/research.conf
COPY research.ini /usr/local/etc/php/conf.d/research.ini
