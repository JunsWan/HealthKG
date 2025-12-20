from neo4j import GraphDatabase

# 替换成你的 Neo4j URI 和账号密码
URI = "neo4j+ssc://88f8ccae.databases.neo4j.io"
AUTH = ("neo4j", "_BAD-vDc9fZjk17xTHjAUWaNPoxGxhh1X9oz2-fDffM")

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
