# pip install flask -------- required module

from tokenize import String
from flask import Flask, request
import psycopg2
from config import BaseConfig
from logger_util import logger
from flask import jsonify
from datetime import datetime, timedelta, timezone
from flask_caching import Cache

from flasgger import Swagger
from flasgger import swag_from
from db_health import db_health_checker

# create database connections

ERROR = "Error: {0}"


def get_snark_conn():
    """Get database connection using enhanced health checker with retry logic"""
    try:
        return db_health_checker.get_connection_with_retry()
    except Exception as error:
        logger.error(ERROR.format(error))
        raise ValueError("System is down. Please try again later.")


config = {
    "DEBUG": BaseConfig.DEBUG,  # Environment-controlled debug mode
    "CACHE_TYPE": "SimpleCache",  # Flask-Caching related configs
    "CACHE_DEFAULT_TIMEOUT": BaseConfig.CACHE_TIMEOUT,
    "JSONIFY_PRETTYPRINT_REGULAR": BaseConfig.DEBUG,  # Pretty print JSON in debug mode
}

# # ![MINA logo](https://cdn-fagpn.nitrocdn.com/nvawPUgmLuenSpEkZxPTWilYhwRGNGyf/assets/static/optimized/rev-e46fd70/wp-content/themes/minaprotocol/img/mina-wordmark-light.svg)
template = {
    "swagger": "2.0",
    "info": {
        "title": "MINA Open API",
        "description": "MINA Open API for leaderboard uptime data. The API's returns the data for SNARK work uptime data. \
        By default API's will provide most recent scores, and historic scores can use retrieved using data-time parameter. \n ##",
        "termsOfService": "https://minaprotocol.com/tos",
        "version": "1.0.1",
    },
    "host": BaseConfig.SWAGGER_HOST,  # overrides localhost:500
    "basePath": "/uptimescore",  # base bash for blueprint registration
    "schemes": ["https", "http"],
    "operationId": "uptimescore",
}

swagger_config = Swagger.DEFAULT_CONFIG
swagger_config["swagger_ui_bundle_js"] = (
    "//unpkg.com/swagger-ui-dist@3.52.5/swagger-ui-bundle.js"
)
swagger_config["swagger_ui_standalone_preset_js"] = (
    "//unpkg.com/swagger-ui-dist@3.52.5/swagger-ui-standalone-preset.js"
)
swagger_config["jquery_js"] = "//unpkg.com/jquery@3.7.1/dist/jquery.min.js"
swagger_config["swagger_ui_css"] = "//unpkg.com/swagger-ui-dist@3.52.5/swagger-ui.css"

# create app instance
app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)
swagger = Swagger(app, template=template, config=swagger_config)

# Health check endpoints for Kubernetes probes
@app.route('/health', methods=['GET'])
def health_check():
    """
    Basic liveness probe endpoint
    Returns 200 if the Flask application is running
    """
    return jsonify({
        'status': 'healthy',
        'service': 'delegation-program-leaderboard-api',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), 200

@app.route('/health/ready', methods=['GET'])
def readiness_check():
    """
    Readiness probe endpoint with database connectivity check
    Returns 200 if the application is ready to serve traffic
    """
    try:
        health_status = db_health_checker.check_database_health()
        
        if health_status['status'] == 'healthy':
            return jsonify({
                'status': 'ready',
                'service': 'delegation-program-leaderboard-api',
                'database': health_status,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 200
        else:
            return jsonify({
                'status': 'not_ready',
                'service': 'delegation-program-leaderboard-api', 
                'database': health_status,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }), 503
            
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return jsonify({
            'status': 'not_ready',
            'service': 'delegation-program-leaderboard-api',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 503

@app.route('/health/debug', methods=['GET'])
def debug_info():
    """
    Debug information endpoint for troubleshooting
    Only available when DEBUG mode is enabled
    """
    if not BaseConfig.DEBUG:
        return jsonify({'error': 'Debug information not available in production mode'}), 403
        
    try:
        db_info = db_health_checker.get_connection_info()
        health_status = db_health_checker.check_database_health()
        
        return jsonify({
            'service': 'delegation-program-leaderboard-api',
            'debug_mode': BaseConfig.DEBUG,
            'logging_level': BaseConfig.LOGGING_LEVEL,
            'database_config': db_info,
            'database_health': health_status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Debug info endpoint failed: {e}")
        return jsonify({
            'service': 'delegation-program-leaderboard-api',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


# 1
def get_current_snark_data_for_all():
    conn = get_snark_conn()
    query = """SELECT block_producer_key , score ,score_percent FROM nodes WHERE application_status = true and score 
    is not null ORDER BY score DESC """
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        result = [
            dict((cursor.description[i][0], str(value)) for i, value in enumerate(row))
            for row in cursor.fetchall()
        ]
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(ERROR.format(error))
        cursor.close()
        return -1
    finally:
        cursor.close()
        conn.close()
    return result


# 2
def get_current_snark_data_for_one(filter_pub_key):
    conn = get_snark_conn()
    query = """select n.block_producer_key , sh.score , sh.score_percent 
        from score_history sh join nodes n on n.id =sh.node_id 
        where n.block_producer_key = %s
        order by score_at desc limit 1	; """
    try:
        cursor = conn.cursor()
        cursor.execute(query, (filter_pub_key,))
        result = [
            dict((cursor.description[i][0], str(value)) for i, value in enumerate(row))
            for row in cursor.fetchall()
        ]
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(ERROR.format(error))
        cursor.close()
        return -1
    finally:
        cursor.close()
        conn.close()
    return result


# 3
def get_historic_snark_data_for_all(score_at):
    conn = get_snark_conn()
    query = """with recent_time as(
                select score_at
                from score_history sh 
                where sh.score_at < %s
                order by sh.score_at desc limit 1
            )
            select n.block_producer_key , sh.score , sh.score_percent 
            from recent_time r join score_history sh on r.score_at=sh.score_at 
            join nodes n on n.id =sh.node_id order by sh.score DESC ; """
    try:
        cursor = conn.cursor()
        cursor.execute(query, (score_at,))
        result = [
            dict((cursor.description[i][0], str(value)) for i, value in enumerate(row))
            for row in cursor.fetchall()
        ]
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(ERROR.format(error))
        cursor.close()
        return -1
    finally:
        cursor.close()
        conn.close()
    return result


# 4
def get_historic_snark_data_for_one(score_at, filter_pub_key):
    conn = get_snark_conn()
    query = """with recent_time as(
                select score_at
                from score_history sh 
                where sh.score_at < %s
                order by sh.score_at desc limit 1
            )
            select n.block_producer_key , sh.score , sh.score_percent 
            from recent_time r join score_history sh on r.score_at=sh.score_at
            join nodes n on n.id =sh.node_id and n.block_producer_key =%s; """
    try:
        cursor = conn.cursor()
        cursor.execute(query, (score_at, filter_pub_key))
        result = [
            dict((cursor.description[i][0], str(value)) for i, value in enumerate(row))
            for row in cursor.fetchall()
        ]
        print(result)
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(ERROR.format(error))
        cursor.close()
        return -1
    finally:
        cursor.close()
        conn.close()
    return result


# path params 1
@app.route("/uptimescore/", endpoint="without_data_type_score_at")
@app.route("/uptimescore/<path:pubkey>", endpoint="with_pubkey")
@app.route("/uptimescore/<path:pubkey>/<path:dataType>/", endpoint="without_score_at")
@app.route("/uptimescore/<path:pubkey>/<path:dataType>/<path:scoreAt>/", endpoint="all")
@swag_from("api_spec_withpubkey.yml", endpoint="with_pubkey")
@swag_from(
    "api_spec_without_data_type_score_at.yml", endpoint="without_data_type_score_at"
)
@swag_from("api_spec_without_score_at.yml", endpoint="without_score_at")
@swag_from("api_spec.yml", endpoint="all")
def get_score(pubkey="", dataType="snarkwork", scoreAt="current"):
    pubkey = pubkey.replace("/", "")
    dataType = dataType.replace("/", "")
    scoreAt = scoreAt.replace("/", "")

    logger.info("dt: {0}, time:{1}, pubkey:{2}".format(dataType, scoreAt, pubkey))
    score_time = None
    filter_pub_key = None

    if pubkey.startswith("B62") and len(pubkey) == 55:
        filter_pub_key = pubkey

    elif pubkey in ["snarkwork"]:
        if dataType not in ["snarkwork"]:
            scoreAt = dataType
        dataType = pubkey

    elif len(pubkey) > 0:
        response = {
            "Error": "Invalid public key",
            "Error_message": "Please provide correct public key",
        }
        return jsonify(response), 404

    if scoreAt != "current":
        try:
            datetime.strptime(scoreAt, "%Y-%m-%dT%H:%M:%SZ")
            score_time = datetime.strptime(scoreAt, "%Y-%m-%dT%H:%M:%SZ")
        except Exception as e:
            response = {
                "Error": "Invalid Date Format",
                "Error_message": "Please make sure you use Valid Date in Format:2022-04-30T08:30:00Z",
            }
            return jsonify(response), 404

    if dataType not in ["snarkwork"]:
        response = {
            "Error": "Invalid datatype",
            "Error_message": "Please provide datatype as snarkwork",
        }
        return jsonify(response), 404

    data = None
    try:
        if "snarkwork" == dataType and score_time is None and filter_pub_key is None:
            data = get_current_snark_data_for_all()

        elif (
            "snarkwork" == dataType
            and score_time is None
            and filter_pub_key is not None
        ):
            data = get_current_snark_data_for_one(filter_pub_key)

        elif (
            "snarkwork" == dataType
            and score_time is not None
            and filter_pub_key is None
        ):
            data = get_historic_snark_data_for_all(score_time)

        elif (
            "snarkwork" == dataType
            and score_time is not None
            and filter_pub_key is not None
        ):
            data = get_historic_snark_data_for_one(score_time, filter_pub_key)

        else:
            response = {
                "Error": "Something went wrong",
                "Error_message": "Please try again with different parameters",
            }
            return jsonify(response), 500
    except ValueError as e:
        response = {
            "Error": "Something went wrong",
            "Error_message": "System is down. Please try again later.",
        }
        return jsonify(response), 500
    if not data:
        response = {
            "Error": "No data found",
            "Error_message": "Please try again with different parameters",
        }
        return jsonify(response), 404
    return jsonify(data)


@app.errorhandler(404)
def handle_exception(e):
    response = {
        "Error": "Page Not Found",
        "Error_message": "Please make sure you use Correct URL",
    }
    return jsonify(response), 404


@app.errorhandler(500)
def handle_exception(e):
    response = {
        "error": "Internal Server Error",
        "error_message": "Something went wrong we are working on it.",
    }
    return jsonify(response), 500


@app.before_request
def disallow_all_get_params():
    if request.args:
        response = {
            "error": "Query parameters are not allowed",
            "error_message": "This application does not support query parameters in requests.",
        }
        return jsonify(response), 400


if __name__ == "__main__":
    app.run(host=BaseConfig.API_HOST, port=BaseConfig.API_PORT, debug=BaseConfig.DEBUG)
