import datetime

from flask import Flask, render_template, request
from google.auth.transport import requests
from google.cloud import datastore
import google.oauth2.id_token

from flask import Flask, request

from google.cloud import datastore

app = Flask(__name__)

datastore_client = datastore.Client()

undo_stack = []  # Used to store the previous commands for UNDO
redo_stack = [] # Used to store the previous commands for REDO

@app.route('/set')
def set_variable():
    variable_name = request.args.get('name')
    variable_value = request.args.get('value')

    # Store the previous value for UNDO
    previous_value = None
    if variable_name in get_variable_names():
        previous_value = get_variable_value(variable_name)
        undo_stack.append(('SET', variable_name, previous_value))
        delete_entity_by_variable_name(variable_name)
    
    else:
        undo_stack.append(('SET', variable_name, previous_value))
        
    # Set the new value
    entity = datastore.Entity(key=datastore_client.key('Variable'))
    entity.update({'name': variable_name, 'value': variable_value})
    datastore_client.put(entity)

    # Return the new value
    return f'{variable_name} = {variable_value}'

@app.route('/get')
def get_variable():
    variable_name = request.args.get('name')
    variable_value = get_variable_value(variable_name)
    return str(variable_value)

@app.route('/unset')
def unset_variable():
    variable_name = request.args.get('name')

    # Store the previous value for UNDO
    previous_value = None
    if variable_name in get_variable_names():
        previous_value = get_variable_value(variable_name)
        undo_stack.append(('UNSET', variable_name, previous_value))

    # Remove the variable
    delete_entity_by_variable_name(variable_name)

    return f'{variable_name} = "None"'

@app.route('/numequalto')
def num_equal_to():
    variable_value = request.args.get('value')

    query = datastore_client.query(kind='Variable')
    query.add_filter('value', '=', variable_value)
    variables = list(query.fetch())

    return str(len(variables))

@app.route('/undo')
def undo():
    if not undo_stack:
        return 'NO COMMANDS'

    # Get the previous command from the stack
    command, variable_name, previous_value = undo_stack.pop()

    if command == 'SET':
        # Store the current value for REDO
        current_value = get_variable_value(variable_name)
        redo_stack.append(('SET', variable_name, current_value))
        delete_entity_by_variable_name(variable_name)

        # Undo the SET command
        if previous_value is not None:
            entity = datastore.Entity(key=datastore_client.key('Variable'))
            entity.update({'name': variable_name,'value': previous_value})
            datastore_client.put(entity)
        

    elif command == 'UNSET':
        # Store the fact that the variable was previously set for REDO
        was_set = variable_name in get_variable_names()
        redo_stack.append(('UNSET', variable_name, None if not was_set else get_variable_value(variable_name)))

        # Undo the UNSET command
        entity = datastore.Entity(key=datastore_client.key('Variable'))
        entity.update({'name': variable_name,'value': previous_value})
        datastore_client.put(entity)

    # Return the name and value of the changed variable
    return f'{variable_name} = {previous_value}'

def get_variable_names():
    query = datastore_client.query(kind='Variable')
    query.projection = ['name']
    variables = query.fetch()
    return [variable['name'] for variable in variables]

def get_variable_value(name):
    # Retrieve variable from Datastore
    query = datastore_client.query(kind='Variable')
    query.add_filter('name', '=', name)
    result = list(query.fetch()) 

    # If variable exists, return its value
    if result:
        return result[0]['value']

    # If variable does not exist, return None
    return None

def delete_entity_by_variable_name(variable_name):
    query = datastore_client.query(kind='Variable')
    query.add_filter('name', '=', variable_name)
    result = list(query.fetch())
    if len(result) > 0:
        datastore_client.delete(result[0].key)  

@app.route('/redo')
def redo():
    if not redo_stack:
        return "NO COMMANDS"
    
    command, variable_name, previous_value = redo_stack.pop()
    
    if command == 'SET':
        delete_entity_by_variable_name(variable_name)
        entity = datastore.Entity(key=datastore_client.key('Variable'))
        entity.update({'name': variable_name, 'value': previous_value})
        datastore_client.put(entity)
        response = f'{variable_name} = {previous_value}'
        
    elif command == 'UNSET':
        delete_entity_by_variable_name(variable_name)
        response = f'{variable_name} = "None"'
        
    return response

@app.route('/end', methods=['GET'])
def end():
    # Clear all data from the datastore
    undo_stack.clear()
    redo_stack.clear()
    query = datastore_client.query(kind='Variable')
    for entity in query.fetch():
        datastore_client.delete(entity.key)
    return 'CLEANED\n'


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
