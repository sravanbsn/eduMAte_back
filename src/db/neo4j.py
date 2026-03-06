import logging
from typing import Optional

from neo4j import AsyncGraphDatabase

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Neo4jDatabase:
    """
    Neo4j connection manager that provides driver instances and handles initial schema setup.
    """

    def __init__(self, uri: str, user: str, password: str):
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: Optional[AsyncGraphDatabase.driver] = None

    async def connect(self):
        try:
            self._driver = AsyncGraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            logger.info("Successfully connected to Neo4j graph database.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j database: {e}")
            raise

    async def close(self):
        if self._driver is not None:
            await self._driver.close()
            logger.info("Neo4j connection closed.")

    async def get_session(self):
        if self._driver is None:
            logger.warning(
                "Attempted to get session without active driver. Connecting..."
            )
            await self.connect()
        return self._driver.session()


neo4j_db = Neo4jDatabase(
    uri="", user="", password=""
)  # Injected later in config/startup


async def init_neo4j_constraints(db: Neo4jDatabase):
    """
    Initialize required Neo4j schemas, such as the base constraint for Concept nodes
    used by the SocraticBridge knowledge graph.
    """
    query = "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE"

    try:
        session = await db.get_session()
        async with session:
            await session.run(query)
            logger.info(
                "Neo4j constraints successfully initialized (Concept uniqueness)."
            )
    except Exception as e:
        logger.error(f"Error initializing Neo4j constraints: {e}")
        raise
