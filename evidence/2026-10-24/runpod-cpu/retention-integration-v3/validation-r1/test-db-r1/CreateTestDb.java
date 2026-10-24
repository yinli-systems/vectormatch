import java.sql.*;
import java.nio.file.*;
import java.time.*;
class CreateTestDb {
 public static void main(String[] a) throws Exception {
  String db=a[0]; if(!db.matches("vectormatch_integration_[0-9]{8}_[a-f0-9]{32}"))throw new IllegalArgumentException("unique dedicated test database required");
  String admin="jdbc:postgresql://127.0.0.1:55432/postgres?user=vectormatch&connectTimeout=5&socketTimeout=30";
  try(Connection c=DriverManager.getConnection(admin);Statement s=c.createStatement()){
   s.setQueryTimeout(30);
   try(ResultSet r=s.executeQuery("SELECT current_database(), current_user, inet_server_port()")){r.next();System.out.println("before database="+r.getString(1)+" user="+r.getString(2)+" port="+r.getInt(3));if(!r.getString(2).equals("vectormatch")||r.getInt(3)!=55432)throw new IllegalStateException("local test role/port mismatch");}
   s.execute("CREATE DATABASE \""+db+"\" OWNER vectormatch TEMPLATE template0");
  }
  try(Connection c=DriverManager.getConnection("jdbc:postgresql://127.0.0.1:55432/"+db+"?user=vectormatch&connectTimeout=5&socketTimeout=30");Statement s=c.createStatement();ResultSet r=s.executeQuery("SELECT count(*) FROM pg_namespace WHERE nspname='vm_projection'")){
   r.next();if(r.getLong(1)!=0)throw new IllegalStateException("new DB not empty of application schema");
  }
  System.out.println("createdDedicatedDatabase="+db+" verifiedApplicationSchemaAbsent=true noExistingDatabaseDropped=true");
 }
}
