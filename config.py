import os
from dotenv import load_dotenv
import sshtunnel

# Load environment variables from .env file
load_dotenv()


class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'

    # Initialize class variables
    tunnel = None

    # Database settings based on environment
    @classmethod
    def get_database_uri(cls):
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
            cls.tunnel = sshtunnel.SSHTunnelForwarder(
                (ssh_host),
                ssh_username=ssh_username,
                ssh_password=ssh_password,
                remote_bind_address=(mysql_host, mysql_port),
                local_bind_address=('127.0.0.1', 0)  # Use a random local port
            )

            cls.tunnel.start()

            # Return connection string to the local tunnel
            return f"mysql+pymysql://{mysql_user}:{mysql_password}@127.0.0.1:{cls.tunnel.local_bind_port}/{mysql_db}"


# Initialize the database URI after the class definition
Config.SQLALCHEMY_DATABASE_URI = Config.get_database_uri()
Config.SQLALCHEMY_TRACK_MODIFICATIONS = False

# Dictionary with different configuration environments
config = {
    'development': Config,
    'production': Config,
    'default': Config
}