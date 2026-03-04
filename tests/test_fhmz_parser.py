from aq_common.fhmz_parser import parse_fhmz_rows


HTML = """
<html><body>
<div class="subtitle">&nbsp;2.3.2026. u 11 <sup>h</sup></div>
<table>
<tr><td colspan="15" class="naslov">SATNE VRIJEDNOSTI POLUTANATA</td></tr>
<tr>
  <td rowspan="2" class="desna">SARAJEVO</td>
  <td class="desna"><a href="amsVijecnica.php">Vijecnica</a></td>
  <td class="IKZ desna"><img src="index/c.png" /></td>
  <td>7</td><td><img src="index/b.png"/></td>
  <td>17</td><td><img src="index/c.png"/></td>
  <td>25</td><td><img src="index/c.png"/></td>
  <td>49</td><td><img src="index/d.png"/></td>
  <td>40</td><td><img src="index/d.png"/></td>
  <td>40</td><td>&nbsp;</td>
</tr>
</table>
</body></html>
"""


def test_parse_single_row():
    _, rows = parse_fhmz_rows(HTML)
    assert len(rows) == 1
    row = rows[0]
    assert row["city_code"] == "SARAJEVO"
    assert row["station_name"] == "Vijecnica"
    assert row["values"]["SO2"] == 7.0
    assert row["values"]["NO2"] == 17.0
    assert row["values"]["O3"] == 25.0
    assert row["values"]["PM10"] == 49.0
    assert row["values"]["PM2.5"] == 40.0
    assert row["values"]["CO"] == 40.0

