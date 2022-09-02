# ElasticSeach Mappings

This directory contains the Elasticsearch index mappings. Each file describes a single index, with
the name of the file matching the name of the index. e.g. `profiles.json` describes the profiles
index.

The mappings file does not describe how the index is populated - only how the search index analyses
and stores the data that is posted to it.

See https://www.elastic.co/guide/en/elasticsearch/reference/7.x/mapping.html for more details on
mapping and index configuration.
