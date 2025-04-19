import os
from dotenv import load_dotenv
import sshtunnel

# Load environment variables from .env file
load_dotenv()


class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

    # Database settings based on environment
    @staticmethod
    def get_database_uri():
        # Check if we're in development or production
        deployment = os.environ.get('DEPLOYMENT_ENVIRONMENT', 'development')

        if deployment == 'production':
            # When running on PythonAnywhere, use direct connection
            return os.environ.get('PROD_DATABASE_URL')
        else:
            # For development, set up the SSH tunnel
            ssh_host = os.environ.get('DEV_SSH_HOST')
            ssh_username = os.environ.get('DEV_SSH_USERNAME')
            ssh_password = os.environ.get('DEV_SSH_PASSWORD')
            mysql_host = os.environ.get('DEV_MYSQL_HOST')
            mysql_port = int(os.environ.get('DEV_MYSQL_PORT', 3306))
            mysql_db = os.environ.get('DEV_MYSQL_DATABASE')
            mysql_user = os.environ.get('DEV_MYSQL_USERNAME')
            mysql_password = os.environ.get('DEV_MYSQL_PASSWORD')

            # Create a global tunnel to use throughout the application
            Config.tunnel = sshtunnel.SSHTunnelForwarder(
                (ssh_host),
                ssh_username=ssh_username,
                ssh_password=ssh_password,
                remote_bind_address=(mysql_host, mysql_port),
                local_bind_address=('127.0.0.1', 0)  # Use a random local port
            )

            Config.tunnel.start()

            # Return connection string to the local tunnel
            return f"mysql+pymysql://{mysql_user}:{mysql_password}@127.0.0.1:{Config.tunnel.local_bind_port}/{mysql_db}"

    SQLALCHEMY_DATABASE_URI = get_database_uri.__func__()
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


# Dictionary with different configuration environments
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}