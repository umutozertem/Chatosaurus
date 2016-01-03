import MySQLdb

def connection():
    conn = MySQLdb.connect(host="localhost",
                           user = "<your mysql username>",
                           passwd = "<your mysql passwd>",
                           db = "chatApp")
						   
    c = conn.cursor()

    return c, conn
