#!/usr/bin/env python3
"""Regenerate georeferenced internal connector paths from the exact frozen network."""
from pathlib import Path
import argparse,json,xml.etree.ElementTree as ET
import libsumo as traci

HERE=Path(__file__).resolve().parent

def build(net):
    tree=ET.parse(net).getroot()
    lanes={lane.get('id'):lane for lane in tree.findall('.//lane')}
    result={}
    traci.start(['sumo','-n',str(net),'--no-step-log','true','--duration-log.disable','true','--no-warnings','true'])
    try:
        # No simulationStep: only the network projection is used.
        for connection in tree.findall('connection'):
            via=connection.get('via')
            if not via:continue
            lane=lanes[via]
            shape=[]
            for point in lane.get('shape').split():
                x,y=map(float,point.split(','));lon,lat=traci.simulation.convertGeo(x,y)
                shape.append([lon,lat])
            key=connection.get('from')+'|'+connection.get('to')
            result.setdefault(key,[]).append(dict(via=via,shape_lonlat=shape))
        assert traci.simulation.getTime()==0
    finally:traci.close()
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--net',type=Path,default=HERE/'inputs/mohali_urban.net.xml')
    parser.add_argument('--output',type=Path,default=HERE/'reruns/connectors.json')
    parser.add_argument('--reference',type=Path,default=HERE.parent/'data/connectors.json')
    args=parser.parse_args();result=build(args.net.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,separators=(',',':')))
    original=json.loads(args.reference.read_text())
    report=dict(passed=result==original,connection_keys=len(result),
                connector_options=sum(map(len,result.values())),
                preserves_xml_option_order=True,simulation_advanced=False,
                exact_geometry_and_option_lists_equal=result==original,
                sumo_version=traci.getVersion())
    args.output.with_name('connectors_verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 2)

if __name__=='__main__':main()
