/*
 * opencog/embodiment/Learning/LearningServerMessages/TrySchemaMessage.h
 *
 * Copyright (C) 2007-2008 Erickson Nascimento
 * All Rights Reserved
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License v3 as
 * published by the Free Software Foundation and including the exceptions
 * at http://opencog.org/wiki/Licenses
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program; if not, write to:
 * Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

#ifndef TRYSCHEMAMESSAGE_H_
#define TRYSCHEMAMESSAGE_H_

#include "Message.h"
#include <opencog/atomspace/AtomSpace.h>

namespace LearningServerMessages {

class TrySchemaMessage : public MessagingSystem::Message {
	
	private:
		std::string schema;
        std::vector<std::string> schemaArguments;
			
		// the full message to be sent
		std::string message;
		
	public:
		
		~TrySchemaMessage();
		TrySchemaMessage(const std::string &from, const std::string &to);
		TrySchemaMessage(const std::string &from, const std::string &to, 
					 const std::string &msg);	
		TrySchemaMessage(const std::string &from, const std::string &to, 
				     const std::string &schema, const std::vector<std::string> &argumentsList) 
                     throw (opencog::InvalidParamException, std::bad_exception);
		
        /**
         * Return A (char *) representation of the message, a c-style string terminated with '\0'.
         * Returned string is a const pointer hence it shaw not be modified and there is no need to
         * free/delete it.
         *
         * @return A (char *) representation of the message, a c-style string terminated with '\0'
         */
        const char *getPlainTextRepresentation();

        /**
         * Factory a message using a c-style (char *) string terminated with `\0`.
         *
         * @param strMessage (char *) representation of the message to be built.
         */
        void loadPlainTextRepresentation(const char *strMessage);
        
        /**
         * Schema getter and setter
         */
       	void setSchema(const std::string &schema); 
        const std::string & getSchema();

        /**
         * Schema arguments get and set methods.
         */
        const std::vector<std::string> &getSchemaArguments();
        void setSchemaArguments(const std::vector<std::string> &argumentsList);

}; // class
}  // namespace
#endif 
