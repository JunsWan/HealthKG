from neo4j import GraphDatabase


URI = "your neo4j url"
AUTH = ("neo4j", "password")

# 如果 SSL 验证有问题，可以加 trust 参数
driver = GraphDatabase.driver(URI, auth=AUTH)

try:
    with driver.session() as session:
        result = session.run("RETURN 1 AS test")
        print("Connection successful, test query returned:", result.single()["test"])
except Exception as e:
    print("Connection failed:", e)
finally:
    driver.close()
