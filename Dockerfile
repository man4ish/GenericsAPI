FROM kbase/sdkbase2:python
MAINTAINER KBase Developer
# -----------------------------------------
# In this section, you can install any system dependencies required
# to run your App.  For instance, you could place an apt-get update or
# install line here, a git checkout to download code, or run any other
# installation scripts.

RUN apt-get update

RUN conda install  -c bioconda python=3.6.3 biom-format

RUN pip uninstall numpy -y \
    && pip install numpy==1.14.5 \
    && pip install networkx==2.1

RUN pip install pandas==0.23.4 \
    && pip install xlrd \
    && pip install openpyxl \
    && pip install xlsxwriter \
    && pip install dotmap \
    && pip install matplotlib \
    && pip install scipy

RUN pip install natsort

RUN conda install -yc bioconda biom-format
RUN pip install sklearn \
    && pip install plotly

RUN pip install mock

# -----------------------------------------

RUN mkdir -p /kb/module/work
RUN chmod -R a+rw /kb/module
# install SigmaJS http://sigmajs.org/
RUN apt-get install wget && \
    cd /kb/module && \
    wget https://github.com/jacomyal/sigma.js/archive/v1.2.1.zip && \
    unzip v1.2.1.zip && \
    rm -rf v1.2.1.zip && \
    mv sigma.js-1.2.1 sigma_js

# -----------------------------------------

COPY ./ /kb/module
WORKDIR /kb/module

RUN make all

ENTRYPOINT [ "./scripts/entrypoint.sh" ]

CMD [ ]
