"""Editor-only node state stored in project glTF extras."""


def selection_nodes(document,selected):
    nodes=document.get('nodes',[]);result=set()
    pending=[selected] if isinstance(selected,int) else list(selected)
    while pending:
        index=pending.pop()
        if index in result or not 0<=index<len(nodes):continue
        result.add(index);pending.extend(nodes[index].get('children',[]))
    return result


def node_state(document,index):
    state=document['nodes'][index].get('extras',{}).get('arika_editor',{})
    return dict(hidden=bool(state.get('hidden',False)),locked=bool(state.get('locked',True)))


def transform_locks(document,index):
    state=document['nodes'][index].get('extras',{}).get('arika_editor',{}).get('transform_locks',{})
    return {key:[bool(v) for v in state.get(key,[False,False,False])[:3]] for key in ('location','rotation','scale')}


def hidden_nodes(document):
    return selection_nodes(document,[i for i in range(len(document.get('nodes',[]))) if node_state(document,i)['hidden']])
