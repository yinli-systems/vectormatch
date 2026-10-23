import java.sql.*;
import java.util.*;
import com.fasterxml.jackson.databind.ObjectMapper;
public final class PgAudit {
  public static void main(String[] args) throws Exception {
    var mapper=new ObjectMapper();
    String cluster="runpod-cloud-20261023-01";
    try(var c=DriverManager.getConnection("jdbc:postgresql://127.0.0.1:55432/postgres","vectormatch","")) {
      c.setReadOnly(true);c.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);c.setAutoCommit(false);
      var cursor=new LinkedHashMap<String,Object>();
      try(var q=c.prepareStatement("SELECT event_seq,market_seq,events_stored,trades_stored,source_last_event_seq FROM vm_projection.cursors WHERE cluster_id=?")) {
        q.setString(1,cluster);try(var r=q.executeQuery()){if(!r.next())throw new AssertionError("Missing cursor");for(int i=1;i<=5;i++)cursor.put(r.getMetaData().getColumnName(i),r.getLong(i));}
      }
      var rows=new ArrayList<Map<String,Object>>();long next=1,market=0,trades=0;
      try(var q=c.prepareStatement("SELECT event_seq,market_seq,event_type,payload::text,payload_sha256 FROM vm_projection.events WHERE cluster_id=? ORDER BY event_seq")) {
        q.setString(1,cluster);try(var r=q.executeQuery()){while(r.next()) {
          long seq=r.getLong(1),m=r.getLong(2);String type=r.getString(3);
          if(seq!=next++)throw new AssertionError("Event gap");if(m>0&&m!=++market)throw new AssertionError("Market gap");
          if(type.equals("TRADE"))trades++;
          var row=new LinkedHashMap<String,Object>();row.put("eventSeq",seq);row.put("marketSeq",m);row.put("type",type);row.put("payload",mapper.readTree(r.getString(4)));row.put("storedPayloadSha256",r.getString(5));rows.add(row);
        }}
      }
      if(!Objects.equals(cursor.get("event_seq"),(long)rows.size()) || !Objects.equals(cursor.get("events_stored"),(long)rows.size()) || !Objects.equals(cursor.get("trades_stored"),trades) || !Objects.equals(cursor.get("market_seq"),market))throw new AssertionError("Cursor/ledger mismatch");
      c.commit();
      System.out.println(mapper.writeValueAsString(Map.of("passed",true,"timestamp",java.time.Instant.now().toString(),"scope","Read-only repeatable-read JDBC transaction; full synthetic ledger, contiguous event/market sequences and cursor/count agreement; no independent payload or source equality proof","clusterId",cluster,"cursor",cursor,"rows",rows)));
    }
  }
}
